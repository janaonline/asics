# ASICS database design (PostgreSQL / Supabase)

For review. **Nothing here is built**: no migrations, no Supabase calls. Words follow
[NAMING.md](NAMING.md) (city, category, section, question, unit, parastatal, ULG, answer, citation,
run). Where this differs from NAMING.md section 3 it says so.

Design rule: a new question, a new parastatal type, a new column in a template or a new calculated
question is **a row, a JSONB key or one Python entry, never a schema change**.

## 1. Question banks and questions

| Table | Columns | Why |
|---|---|---|
| `categories` | `id`, `name` (`ulg`, `parastatal`), `title`, `unit_kind` (`ulg`/`parastatal`), `scoring_code` | As NAMING.md. A third category is a row. |
| `question_banks` | `id`, `category_id`, `version`, `source_file_name`, `source_sha256`, `content_hash`, `built_at`, `imported_at`, `is_current` | One row per bank version (the app's `bank_version.py` already makes `<source>@<date>#<hash8>`). `UNIQUE (category_id, version)`, one `is_current` per category (partial unique index). |
| `questions` | `id`, `bank_id`, `code` (`UPD 1a`), `raw_id`, `section` (`UPD`/`SC`/`DPG`), `tag` (`MQ`/`SQ`), `tag_inferred`, `parent_question_id`, `position`, `text`, `max_score numeric NULL`, `assessment_level`, `unit_of_assessment`, `applicability`, `methodology`, `evidence_requirement`, `rationale`, `unit_kind`, `extra_fields jsonb` | Copied exactly from the bank. `max_score` is nullable (DPG 4 is not scored). `extra_fields` takes any column a bank gains later (the loader already keeps these on `Question.extra`). A standalone MQ is *derived* (an MQ with no children), never stored. `unit_kind` is copied from the category so scores can be checked (section 5). |

* **Uniqueness**: `UNIQUE (bank_id, code)`. Because `bank_id` fixes category and version this is
  per (category, bank version, code); the ULG will reuse codes such as `UPD 1a` without clashing.
* **How a city is tied to a bank**: a bank per category (`is_current`), plus an optional
  `city_bank_assignments (city_id, category_id, bank_id)` that overrides it for one city. Every
  run records the `bank_id` it used (section 11), so old results never silently change.
* **Open decision**: may a city ever have its own extra questions? Options: (a) a city-specific
  bank row (`question_banks.city_id` nullable), (b) `questions.city_id` nullable. Neither is needed
  today; (a) needs no change to `questions`.

## 2. Cities

`cities (id, slug UNIQUE, name, state, aliases text[], ulg_name, include bool, created_at)`.
`aliases` carries "Bangalore" for Bengaluru (today the register's "Other names").

## 3. Parastatal types and parastatals

| Table | Columns | Why |
|---|---|---|
| `parastatal_types` | `code PK`, `label`, `old_codes text[]`, `sort_order`, `active` | A new type is a row. Today: `development_authority`, `water_supply_entity`, `public_bus_transport_operator`, `other`. `old_codes` holds `water_supply_board`, `transport_corporation` for reading old files. |
| `parastatals` | `id`, `city_id`, `short_code` (BWSSB), `name`, `type_code` FK, `revenue_raising`, `capex_mandate`, `has_annual_budget`, `has_chief_executive` (bool), `include`, `found_by`, `why_included`, `official_website`, `governing_act`, `notes` | `UNIQUE (city_id, short_code)`. The four flags stay (they decide SC 1, 2, 3, 11). |

`ulg` is **not** a row in `parastatal_types`. In the code the ULG unit is still a `Parastatal`
object with type `ulg` (one constant, `parastatal_types.ULG_TYPE`; also `categories.ULG_UNIT_ID =
"ULG"`, `costs.py` and `sources_master.py` build fake `other` units). For the database the ULG is an
`assessed_unit` of kind `ulg` (section 5). Not redesigned now.

## 4. Applicability as data

| Table | Columns |
|---|---|
| `applicability_phrases` | `id`, `position`, `phrase`, `rule` (`type_is`/`type_is_not`/`flag`/`common`), `type_code NULL`, `flag_name NULL` (the file `data/applicability_rules.yaml`, first match wins) |
| `question_applicability` | `question_id`, `rule`, `type_code NULL`, `flag_name NULL`, `source` (`text`/`override`), `confirm_note NULL` |

The question's applicability text stays in `questions.applicability`; the resolved rule is a row
(`override` rows carry the CONFIRM note, e.g. UPD 3b). A question with a flag rule applies to a
unit when `parastatals.<flag>` is true; a type rule when `type_code` matches. A view
`question_applies (unit_id, question_id)` evaluates them.

## 5. Units

`assessed_units` is what answers and scores point to (`unit_id NOT NULL` everywhere).

| | **A. NAMING.md `units`** | **B. Supertype (recommended)** |
|---|---|---|
| Shape | `units (id, city_id, category_id, unit_type, parastatal_id NULL)` | `assessed_units (id, city_id, kind, name)` + `parastatals.unit_id UNIQUE FK` |
| Constraints | `CHECK ((unit_type='ulg') = (parastatal_id IS NULL))`; `UNIQUE (city_id, category_id, parastatal_id)` (parastatals); partial `UNIQUE (city_id, category_id) WHERE unit_type='ulg'` | partial `UNIQUE (city_id) WHERE kind='ulg'`; `UNIQUE (id, kind)`; `parastatals (unit_id, 'parastatal')` composite-FK to `(id, kind)` so a parastatal row cannot point at a ULG unit |
| Weak point | nullable FK and two uniqueness mechanisms; `category_id` repeats what `unit_type` implies | one more table; ULG has no subtype row |

**Recommend B**: no NULL-in-unique trap, one FK target, parastatal facts stay on `parastatals`.
To stop a ULG question being scored for a parastatal: `questions.unit_kind` and
`assessed_units.kind` are copied onto `scores`/`answers` and `FOREIGN KEY (unit_id, unit_kind)` /
`(question_id, unit_kind)` plus `CHECK` keep them equal (no triggers).

## 6. Sources and citations

`sources (id, city_id, unit_id NULL, citation_code, url, title, source_type, useful_for,
question_codes text[], accessibility, current_status, verification_status, authority_score,
provenance, found_by, use_for_answers, team_notes, notes, content_hash, snapshot_path, checked_at,
run_id)`; `UNIQUE (city_id, citation_code)` (`BWSSB-07`); `unit_id NULL` = shared by every unit of
the city. Snapshots and extracted text go to Supabase Storage; `snapshot_path` is the object key.

Existing SQLite `links.db` (one per city for Step 1, one per Step 2 run; **write-only** today,
nothing reads it):

| SQLite table.column | Goes to |
|---|---|
| `sources.key, citation_id, parastatal_id, title, url, source_type, useful_for, question_ids, accessibility, current_status, verification_status, authority_score, provenance, found_by, use_for_answers, notes, content_path, checked_at` | `sources` (`key` = hash of unit+url: use as a unique helper; `content_path` -> `snapshot_path`). `team_notes` come from the Sources workbook, not `links.db` |
| `tool_urls.url` | `run_urls (run_id, url)` (about 6,000 per city run) |
| `answers.parastatal_id, question_id, status, proposed_score, answer, citation_id, citation, citation_url, evidence_excerpt, notes` | `answers` (a subset) |
| `issues.phase, severity, message, ref` | `run_events` |

## 7. Answers (Step 2 research)

`answers (id, run_id, unit_id, question_id, status, answer_text, proposed_score numeric NULL,
answer_class, confidence, rubric_band, citation_id FK sources NULL, evidence_excerpt, notes,
missing_evidence, where_to_find, search_phrase, memory_used text[], created_at)`.
`UNIQUE (run_id, unit_id, question_id)`. `status` = the 7 statuses; `answer_class` in
`A1 A2 R P M 'Needs review'`; `confidence` in `High Medium Low`. `question_id` is a question of the
bank version the run used. Research stays separate from scores: `proposed_score` is only the
Step 2 proposal.

## 8. Scores

`scores (id, unit_id, question_id, scorer_type, scorer, score numeric NOT NULL, inputs jsonb,
calculated jsonb, scorer_comments, chapter, provision, clause, page_number, source_link,
latest_information, additional_comments, answer_id NULL, run_id NULL, import_id NULL,
golden_status, created_at, updated_at)`.

* `scorer_type` in `ai | human | expert`; `scorer` is a model name for AI, a person for human/expert.
* **No row without a score** (blank = not scored, never 0). `score NOT NULL`; an unscored template
  row creates nothing.
* `inputs` = the typed question-specific columns (SC 1 yearly figures, DPG 1a scenario, DPG 2b / 7a
  Yes/No parts) **and any extra column** a city's template has, keyed by header text; `calculated`
  = the template's helper values (e.g. average own revenue %). No column per question input.
* `UNIQUE (unit_id, question_id, scorer_type, scorer)` makes re-importing an upsert.
* **View `final_scores`**: expert, else human (the approved golden one; if two humans differ, none:
  it is a conflict), else AI. This is **more than the repo does today**: `ai.py` writes
  `Final score = ★ Your score (expert) else AI score` and `Score used` = `Expert (overrides AI)` /
  `AI` / `Not scored yet`; interns' (human) scores are shown beside the AI's on the results page,
  not used in "Final". Whether human scores should feed the final score is an open decision.

## 9. Calculated scores

Formulas read from the templates (`t` = same-row table, three years Yr1-Yr3):

| Q | Inputs | Helper | Score |
|---|---|---|---|
| SC 1 | per year: own revenue, other revenue, capital receipts, revenue exp., capital exp. (Rs crore) | own revenue % = own revenue / (revenue exp. + capital exp.) when numbers exist and the denominator > 0; years with any data; years with valid data; average % | blank if no year has data; 0 if fewer than 2 valid years; else `MIN(10, average % x 10)` (other revenue and capital receipts are collected, not used) |
| SC 2 | per year: capital exp., population 2011 (lakh); benchmark (highest per-capita capex of same type) | per-capita capex = capex / population x 100 (population > 0); counts; average | blank / 0 as SC 1; else if benchmark > 0 `MIN(10, average / benchmark x 10)` else blank |
| SC 3 | per year: budgeted income BE, actual income | variance % = ABS(actual - BE) / BE (BE > 0); counts; average | blank / 0 as SC 1; else 10 if average variance <= 0.15, else 0 |
| SC 11 | chief executives in last five years (count) | summary | blank if < 1; 10 if 1; 5 if 2-3; else 0 |
| SC 12b | women staff, total staff, benchmark % | proportion % | `proportion / benchmark x 5` when both numbers and benchmark > 0 (not capped: template flags a score above max) |
| DPG 1a | scenario A/B/C; "Acts explicit and non-overlapping" Yes/No | summary | 5 if A; else 5 if Yes, 0 if No; blank otherwise |
| DPG 2b | plans, budgets, reports tabled: Yes/No each | summary | 5 if 3 Yes, else Yes x 1.67; blank if none answered |
| DPG 7a | web channel, telephone channel, acknowledgement/tracking: Yes/No each | summary | 3.33 if 3 Yes, else Yes x 1.11; blank if none answered |

(SC 12a is typed, not calculated.) **Proposal**: one Python module `src/asics_agent/scoring/calculated.py`
with a registry `{question code: Calculation(inputs, helpers, score)}`; the importer calls it for the
codes in the registry and stores the result beside the inputs in `scores.inputs`/`calculated`. Tests
fill the template inputs, recalculate with LibreOffice (`recalc.py`) and require the module's score to
equal Excel's. A new calculated question = one registry entry plus its test case. The exact
definition of a "valid year" and the DPG 2b/7a summary text must be copied from the cell formulas
at build time, not from this table.

## 10. Rollups as SQL views (to be confirmed by the program team)

Not stored. From the City Summary sheets and `Implementation_Note.md`:

| View | Rule |
|---|---|
| `mq_scores` | MQ = sum of its sub-questions' scores; counted **only when all applicable sub-questions are scored**; a standalone MQ is its own score |
| `mq_attainable_max` | sum of `max_score` of the applicable sub-questions (so UPD 2 can be worth 5, not 10, to a parastatal) |
| `city_question_values` | value = average over the applicable parastatals; counted **only when all of them are scored**; `NA` when none applicable |
| `section_scores` | out of 10 = sum of scored MQs / their attainable max x 10 |
| `city_totals` | total = average of UPD, DPG, SC, shown only when all three exist |

All marked **to be confirmed by the program team**, with the note's own open items (pooled vs
averaged "all questions"; DPG 4 left out of every max; benchmark scope).

## 11. Runs, events, reviews

| Table | Columns |
|---|---|
| `runs` | `id`, `step` (1/2/3), `category_id`, `bank_id`, `started_at`, `finished_at`, `status`, `model`, `effort`, `agent_setup_fingerprint`, `options jsonb`, `cost_usd`, `started_by`; `run_cities (run_id, city_id)` |
| `run_events` | `id`, `run_id`, `phase`, `severity`, `message`, `ref`, `audience` (`team`/`developer`) |
| `reviews` | `id`, `target_type`, `target_id`, `reviewer`, `decision`, `note`, `reviewed_at` (replaces Sources-workbook edits) |

`runs.bank_id` and `agent_setup_fingerprint` are what let results be compared across a prompt,
model or bank change. Today the app records the bank version in `run_summary.json` (Step 2) and a
`<workbook>.bank_version.json` next to the Step 3 AI workbook. **Memory notes, prompts and skills
stay in git for now**; only the fingerprint is stored.

## 12. LangGraph state

The graphs run with an in-memory checkpointer (`runner.py`: `InMemorySaver` with a serializer that
allows the pydantic models in `MasterState`: questions, parastatals, sources, answers, issues).
A Postgres checkpointer would need `langgraph-checkpoint-postgres`, its own tables (it creates them
itself) and the same allowed-types list. Recommendation: keep in-memory until runs must resume
after a restart; the database holds results, not graph state. **To verify, not assumed**: which
Supabase connection mode (session vs transaction pooler vs direct) the checkpointer supports,
prepared-statement limits in transaction mode, and connection limits for the app's worker threads.

## 13. Template import contract

**Today's defaults** (a city's file may differ; the importer must use the tolerant rules below):
sheet name = question code (cell next to "Question Code" also holds it); table header on row 13;
table `t_<code without spaces>`; columns `City`, `Parastatal Name` (holds the *short code*),
`Parastatal Type`, `Question Code`, `Max Score`, `Score`, `Chapter`, `Provision`, `Clause`,
`Page Number`, `Scorer Comments (Why the score was given)`, `Additional Comments`,
`Source Link or Evidence Document`, `Latest Information (FY or Year or Date)`; question inputs are
the extra columns before `Score`; `Configuration` `tblConfig` = `City`, `Parastatal Type`,
`Parastatal Name`, `Active`.

**Tolerant rules** (implemented in `scoring/template_import.py`): find the table by sheet name /
code cell and by header text, not row 13 or letters; accept renamed or reordered columns through an
alias list per field; keep unknown columns as extra inputs (typed) or calculated values (formulas);
skip non-question sheets and report ones it cannot classify; report per city and question what was
read, ignored and why; one bad sheet or row never stops the rest.

Importer checks (database side): `Record Check` is OK (CHECK rows are reported, not stored);
no duplicate City + Parastatal (the first row is used); the city and parastatal exist (unknown ones
go to a review list, never created); a row with no score stores nothing (never 0); a formula
with no saved value is reported ("open in Excel and save"). Every file gets an **import report**:
rows read, rows skipped and why, unknown columns, unknown questions. Importing the same file twice
does not duplicate rows (upsert on `scores`' unique key; `imports (id, file_name, sha256, imported_at,
imported_by)` also lets the same hash be refused). Filled templates create `scorer_type = human`
rows. The AI's Step 3 files (`scoring/2027/ai/<CATEGORY>_<SECTION>_AI.xlsx`) have the same layout and are read by the
same importer: they create `scorer_type = ai` rows (scorer "AI"; model, prompt fingerprint, bank version and
template hash are in the file's `.ai_info.json`, to be stored on `runs`). **Who the scorer is**: the portal's upload asks for it (typed, never taken from the file name) and
stores it in the submission's sidecar; the reader still falls back to a `Scorer` column or the file
name for files read outside the portal. Open decision 5 (a Scorer column in the templates) remains.

**Submissions (files today, tables later).** Each uploaded file is stored unchanged as
`scoring/2027/human/<category>/<section>/submissions/<timestamp>_<scorer>_<hash8>.xlsx` with a
sidecar (`source = human`, `scorer`, `uploaded_by`, `uploaded_at`, `file_sha256`, `template_sha256`,
`bank_version`, rows read, issues) and an `index.json` registry rebuilt from the sidecars. The same
hash is refused. The importer to the database can read these folders as they are:
`submissions` rows (NAMING.md) and `scores` rows with `scorer_type = human`. **Merge rules**
(`scoring/human_merge.py`) that the database must keep: a blank never overwrites a value; the same
scorer's later file replaces only their earlier values for the rows it contains; two different scorers
with different scores or inputs for one (unit, question) are a `score_conflicts` row, never
resolved automatically, and that unit-question has no human score until resolved; a calculated question is
merged only when every input its Score needs has a value. **Names that the register does not know** (`scoring/name_resolution.py`): the upload preview lists every
city and parastatal as written in the file with its register match (exact, an Other name, a close
spelling, none) and a choice: map to an existing one, add as new (people's scoring only; state and type
are asked, never invented), or skip. The choices are stored in the submission's sidecar (`decisions`;
a later change moves the old ones to `decision_history`), are pre-filled for later uploads of the same
spelling, and every merge uses them. A new or unmatched place is merged and flagged "Not in register - AI
cannot score yet"; nothing is dropped, and skipped rows are listed. Database: `name_decisions`,
`parastatal_aliases` (NAMING.md). Names compare after folding case, spaces and dashes.
**Approval, for a later task** (not built):
an append-only `reviews.jsonl` (or the `reviews` table) with `{when, by, submission_id, sheet, row (or the
whole submission), status: approved | rejected, note}`; the latest entry wins; "submitted" is implicit for
every stored file (= `golden_status = candidate`). Files never change, so a review of a row stays valid.

## 14. Golden data

* `scores.golden_status` in `candidate | approved | retired`, with `golden_approved_by`,
  `golden_approved_at`, `golden_reason`. Only an expert or the research lead may approve (enforced
  in the application and by a row-level policy).
* **Golden sets** (`golden_sets (id, name, bank_id, frozen_at, created_by)`, `golden_set_items
  (set_id, score_id)`) are frozen per bank version, e.g. `bengaluru-parastatal-2026-11`. A later edit
  creates a new set; it never overwrites.
* **Two humans disagree**: both rows stay (`scorer` differs); `score_conflicts (unit_id,
  question_id, status open/resolved, resolution_score_id)` is filled by the same check as today's
  merge step ("Needs a look"). An unresolved conflict is never golden; resolution is an `expert`
  row or an approval of one human row.
* **What counts as golden**: score, inputs, source reference (link, chapter, provision, clause,
  page) and comments. The template has no free-text answer, so the **human answer** is: for a typed
  question the score and the source it cites; for a calculated question the inputs (the score
  follows from them); for a Yes/No question the Yes/No parts.
* **Bank version changes**: golden rows for a question whose text, max score, applicability or
  methodology changed get `stale = true` (a view compares `questions` across banks); never deleted.
  The reuse of a code for a different question (e.g. old `DPG d` is new 5e) is what this protects.
* Re-importing the same file never duplicates golden rows (golden is a status on the unique
  `scores` row, not a copy).

## 15. AI vs golden comparison (views, not tables)

* `ai_vs_golden (unit, question, golden score, AI score, difference, agrees, same_source,
  ai_class, ai_confidence, run_id)`: joins the approved golden `scores` row with the AI `scores` row
  (and its `answers` row). `same_source` = same URL after normalising scheme, `www`, trailing
  slash, fragment and tracking parameters (`compare.normalise_url`).
* `agreement_by_section`, `_by_class`, `_by_parastatal_type`, `_by_city`, `_by_run`: counts and %
  agree, with a percentage only from N compared rows (setting, default 20).
* **Tying a result to what produced it**: `scores.run_id -> runs (model, effort,
  agent_setup_fingerprint, bank_id)`. Comparing two runs' agreement with the same golden set shows
  whether a prompt or model change helped.
* **"Agrees" rule**: exact match is the default (as `scores.py` "Same score?", tolerance 1e-9;
  note the Excel "Agrees with AI?" column uses 0.001). **Open decision**, not chosen silently:
  (a) exact, (b) within a tolerance, (c) same band (bands from the methodology), (d) same source
  as well.
* **Not compared yet**: answer wording (the human template has none) and inputs beyond
  display. Comparing wording would need a human-written answer field or a rubric-based judge
  with its own validation; comparing inputs would need agreed input names across AI and templates.

## 16. Open decisions and what this design does not cover

| # | Decision for the program team / lead |
|---|---|
| 1 | May a city have its own extra questions (section 1)? |
| 2 | Who may approve golden data (expert only, or the research lead too)? |
| 3 | May golden include scores typed directly in the app later (needs a `source` on `scores`)? |
| 4 | Minimum compared rows before percentages show (default 20) |
| 5 | Add a **Scorer** column to the templates, or use file/tab name? |
| 6 | Should human scores feed `final_scores` (today only expert over AI)? |
| 7 | Which "agrees" rule (section 15)? |
| 8 | Confirm UPD 3b = Water Supply Entity only; SC 1/2/3/11 are decided by the register's flags (the templates mark them applicable to all types) |
| 9 | Rollup rules (section 10) and the note's open items |

**Not covered**: uploads for the ULG (it has no templates yet); the ULG question bank and its SC/DPG sections, and ULG scoring templates (Step 3 for ULG still uses the older workbook path); per-section answer agents; the
reviewer workflow beyond `reviews`; users and permissions (use Supabase Auth; golden approval needs a
role); where `Sources` workbook team edits live until `reviews` replaces them; and
how existing outputs/ files are back-filled (they carry no bank version: fingerprint the embedded
"Question Bank" sheet).
