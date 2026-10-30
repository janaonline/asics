# ASICS naming

For review. This file fixes the words the code, the files and the future PostgreSQL database use.
It contains no migrations and no SQL scripts, only proposed names.

## 1. Glossary

| Word | Meaning |
|---|---|
| **city** | One of the cities in the city register (e.g. Bengaluru, Surat). The team chooses the city first. |
| **category** | What kind of assessment is done in a city. There are two: **ULG** and **Parastatal**. The team chooses the category second. Settings: `agent_setup/categories/<name>.md`. |
| **section** | A group of questions *inside* a category's question bank: UPD, SC, DPG. A section is not a category. Parastatal has UPD, SC and DPG. ULG has UPD today; SC and DPG are coming. A question's section is the prefix of its code (`UPD 1a` is in section UPD). |
| **question** | One row of a question bank, with a code such as `UPD 1a` or `DPG 5b`. The same question codes are used in every city. |
| **unit** | What gets assessed. A unit is either one **parastatal** of a city or the city's **ULG**. |
| **parastatal** | A public agency that serves a city (water supply board, transport corporation, development authority…). The parastatals differ between cities. |
| **ULG** | Urban Local Government: the city's own municipal body. |
| **answer** | The Step 2 result for one question about one unit, with its status, text, confidence and the citation it relies on. |
| **citation** | One official source (a row of the Citation Sheet) an answer relies on, with a verbatim quote and a saved copy of the page. |
| **run** | One execution of a step (Step 1 find sources, Step 2 answer, Step 3 score) for one or more cities and categories. |

## 2. The rule

> A **unit** is what gets assessed.
> An **answer** belongs to **(city, category, unit, question)**.

| Category | Units in a city | Answered |
|---|---|---|
| **Parastatal** | the city's parastatals (differ between cities) | each applicable question, separately for every parastatal |
| **ULG** | exactly **one** unit per city, `unit_type = 'ulg'` | each question, once per city |

Today the code stores the ULG unit as a `Parastatal` object with id `ULG`. Section 4 lists every
place that does so. These names (`unit`, `unit_type`) are the target for the database; the Python
field names (`parastatal_id` and friends) are left as they are for now.

### Names used in the code (after the rename)

| Concept | Value or name |
|---|---|
| category names | `ulg`, `parastatal` (setting `ASICS_CATEGORY`, option `--category`) |
| unit values (setting `unit:`) | `ulg`, `parastatal` |
| ULG unit id | `ULG` (`ULG_UNIT_ID`) |
| settings files | `agent_setup/categories/ulg.md`, `agent_setup/categories/parastatal.md` |
| scoring code | `scoring_code`: `UPD` for ULG (interim, keeps `UPD_ai.xlsx` etc.), `PARASTATAL` |
| outputs folders | `outputs/ULG/`, `outputs/Parastatal/` |
| section guidance | `skills/sections/<category>/<code>.md`, shared `skills/sections/<code>.md` |
| memory notes | `memory/categories/<category>/` |

The scoring code `UPD` for ULG is only a file-name prefix kept so existing scoring workbooks are
not renamed. It is not a category and not the section. It should become `ULG` when the SC and DPG
questions arrive.

## 3. Proposed PostgreSQL names

snake_case, plural table names, `id` primary keys, `<table>_id` foreign keys. Nothing here has
been built.

### `cities`
`id`, `slug` (unique), `name`, `state`, `ulg_name`, `aliases` (text[]), `created_at`.

### `categories`
`id`, `name` (unique: `ulg`, `parastatal`), `title`, `unit_type` (`ulg` | `parastatal`),
`scoring_code`, `question_bank_ref`, `description`.

### `sections`
`id`, `category_id` → categories, `code` (`UPD`, `SC`, `DPG`), `title`, `position`.
`UNIQUE (category_id, code)`. UPD appears once per category that has UPD questions.

### `questions`
`id`, `category_id` → categories, `section_id` → sections, `code` (`UPD 1a`), `parent_question_id`
(self, for sub-questions), `kind` (`mq` | `sq`), `text`, `max_score`, `assessment_level`,
`applicability`, `methodology`, `evidence_requirement`, `position`.
`UNIQUE (category_id, code)`.

### `parastatals`
`id`, `city_id` → cities, `code` (e.g. `BWSSB`), `name`, `parastatal_type`, `revenue_raising`,
`capex_mandate`, `has_annual_budget`, `has_chief_executive`, `official_website`, `governing_act`,
`include` (team decision), `found_by`. `UNIQUE (city_id, code)`.

### `units`
`id`, `city_id` → cities, `category_id` → categories, `unit_type` (`ulg` | `parastatal`),
`parastatal_id` → parastatals (null for the ULG), `name`.
- `CHECK ((unit_type = 'ulg') = (parastatal_id IS NULL))`
- `UNIQUE (city_id, category_id, parastatal_id)` for parastatal units, plus a partial unique index
  `UNIQUE (city_id, category_id) WHERE unit_type = 'ulg'`: exactly one ULG unit per city.

The ULG gets a real `units` row instead of being a fake parastatal.

### `runs`
`id`, `step` (1 | 2 | 3), `category_id`, `started_at`, `finished_at`, `status`, `options` (jsonb),
`cost_usd`, `started_by`. A run covering several cities is linked by `run_cities (run_id, city_id)`.

### `citations`
`id`, `run_id` → runs, `city_id`, `unit_id` → units (null = shared by every unit of the city),
`citation_code` (`C-01`), `title`, `source_type`, `url`, `verification_status`, `use_for_answers`,
`saved_copy_path`, `content_hash`, `checked_at`.

### `answers`
`id`, `run_id`, `city_id`, `category_id`, `unit_id` → units, `question_id` → questions, `status`,
`answer_text`, `confidence`, `citation_id` → citations, `quote`, `needs_review`, `created_at`.

**Unique constraint that works for both categories**

```
UNIQUE (run_id, city_id, category_id, unit_id, question_id)
```

`unit_id` is `NOT NULL` for both categories (for ULG it is the city's single `ulg` unit), so no
NULL-in-unique trap. In the Parastatal category there is one row per parastatal; in ULG there is
exactly one row per question. A composite foreign key
`(city_id, category_id, unit_id) → units (city_id, category_id, id)` keeps an answer from pointing
at another city's unit, and `question_id` must belong to the same category.

### `answer_scores` (Step 3, needed beside `answers`)
`id`, `answer_id` → answers, `scorer` (`ai` | person), `score`, `confidence`, `comment`, `scored_at`.

### `reviews`
`id`, `target_type` (`citation` | `answer` | `parastatal`), `target_id`, `reviewer`, `decision`,
`note`, `reviewed_at`. Replaces today's Sources-workbook edits (Include?, Use for Answers?).

## 4. Where the code treats the ULG as a fake parastatal

To clean before the database. Pipeline, scoring and applicability logic have not been changed by
the rename; these are the places that would change.

**Models**
- `models.py`: the ULG is a `Parastatal` (`id="ULG"`, `type="ulg"`); `ParastatalType` includes
  `ulg`. `Answer.parastatal_id`, `Source.parastatal_id` hold the unit id for the ULG too.
  `ALL_PARASTATALS` ("All parastatals") is the shared-by-every-unit marker.

**Step 1**
- `agents/parastatal_discovery.py`: `ulg()` builds `Parastatal(id=ULG_UNIT_ID)`; the node is called
  `profile_parastatal`, the phase `parastatal_checks`, and the profiler is described as "profiled
  like a parastatal".
- `costs.py` (`city_units`): a second, *different* hard-coded `Parastatal(id="ULG", type="other")`
  for cost estimates.
- `agents/sources_master.py`: parastatal wording in the review pause (skipped for ULG); `shared_laws`
  runs only for `unit == "parastatal"`; task and row keys `parastatal`, `parastatal_id`.
- `agents/links_builder.py`: "one run per parastatal", prompt text "every parastatal", progress keyed
  on `task["parastatal"]`.
- `agents/initial_checks.py`, `agents/common.py`, `agents/state.py`: `known_parastatals`,
  `ParastatalTask`, `assess_source(parastatal)`, applicability matrix phase `parastatal_checks`.
- `agents/rollup.py`: "for this parastatal type".

**Step 2**
- `agents/sections/base.py`: default `unit_label="Parastatal"`, error text "no usable source for
  this parastatal", `MemoryScope(parastatals=[…])`.
- `applicability.py`: rules take a `Parastatal`; for the ULG `revenue_raising` and `capex_mandate`
  default to False, so SC and DPG questions that use those rules would be dropped for the ULG.
  `has_annual_budget` / `has_chief_executive` are never refreshed for the ULG unit.
- `workbook.py`, `sources_workbook.py`: the code uses the names `Parastatal`, `Parastatal ID`,
  `Parastatal Type` and sheet "Parastatals" for the ULG too (about 80 mentions). The **files** written for the
  ULG category now say "ULG" instead (`ULG ID`, `ULG Name`, `ULG Type`, `ULG`, sheet "ULG"; same columns, same
  order): `relabel_unit` renames them when a workbook is saved, `canonical_header` reads either spelling.
  Parastatal-category files are unchanged; ULG files written earlier keep loading and get the new headers the
  next time they are rewritten.
- `cities.py`: register sheet "Parastatals", `Parastatal ID`; the type dropdown has "City government"
  as a parastatal type.
- `runner.py`: progress text ("Found the city's parastatals…") and the node name `profile_parastatal`.
- `city_view_page.py`: reads the `Parastatal` column and `Parastatals` sheet (`groupby(["Parastatal", …])`). The
  tab, metric, filters, Coverage text and table headers say "ULG" for the ULG category (`show()` renames the
  columns for display; `read_sheet` reads either spelling).
- `agent_setup/prompts/city-profile.md` starts with `TASK: parastatal_profile` and
  `practice.py` branches on that task name.

**Step 3 (scoring)**
- `scoring/ai.py`: citations are filtered by `Source.parastatal_id`; the "missing agencies" check
  compares `found.parastatals` to the task's agency.
- `scoring/phase2.py`: `CityEvidence.parastatals`; answers keyed by the column `Parastatal`.
- `scoring/skeleton.py`: `Unit.agency: Parastatal`, `gather_units` uses `city.parastatals`, the
  `City | Agencies | … score` summary sheet.
- ULG scoring-workbook rows are bare city names which the code maps to unit `ULG`
  (`scoring/workflow.py` `unit_of`).

## 5. Open points for the program team

- The SC and DPG sections for ULG arrive next week. A ULG question bank needs a section header row
  with `(CODE)` before each section; otherwise every row is forced into the first section.
- A different answer agent *per section* is not supported (the agent is per category).
- Shared section guidance (`skills/sections/{upd,dpg,sc}.md`) is written for parastatals; ULG needs
  its own file per section under `skills/sections/ulg/`.
- The ULG scoring code is still `UPD`; rename it to `ULG` together with the scoring workbooks.
