# ASICS prompt guide

Written 11 Nov 2026 for the program team, P&I and leadership. Plain English. No code knowledge needed.

**How to read the marks.** **[V]** = I read the file or the code and checked it. **[A]** = my assumption; I could not check it. Where a claim has no mark, the mark at the end of its line or table row covers it.

**What this guide is not.** It does not change any prompt, skill, agent or code. It describes what the files say today. Every "Known gaps" line is a fact I checked, not a fix I made.

---

## 1. How the AI works here (half a page)

A **prompt** is a written instruction for the AI, like a job description. In this app the prompts are plain text files in the folder `agent_setup/`. Change a file and the next run uses the new text. No developer is needed for that.

An **agent** is one AI worker with one job. Each agent has a prompt (what to do), some **skills** (help notes it reads first), some **tools** (for example, "search the web" or "read one source") and a few settings. Each call starts fresh: the agent does not remember earlier questions. The app gives it **team notes** (called "memory") where they apply [V].

Before every task, each agent is also handed the **shared rules**: how to treat links, evidence, the methodology and the cut-off date. The order is: shared rules, then skills, then the task prompt, then (in the message) team notes and the task input [V].

**The three steps, in order**

| Step | Job | Who or what runs it | Where people check |
|---|---|---|---|
| 1. Find sources | Find the parastatals of a city, learn about each one, and collect the official documents (the **Citation Sheet**). | AI agents: find parastatals, profile each one, find sources, and judge each source (the ULG has its own profile and source-finder). **Code** then opens every link and tests whether a person could read it. | The team ticks which parastatals to research. The team then reviews the Citation Sheet in the Sources workbook: it can switch a source off ("Use for Answers? = No"), add its own, and fix links. |
| 2. Answer | Answer each question for each parastatal (ULG: once per city), using only the Citation Sheet. | One AI agent per question and parastatal. **Code** checks that the quote is word for word in the source. | The team reads the answers workbook. Rows marked "Human Verification Required", "Partially Answered" or "Insufficient Evidence" need a person. |
| 3. Score | Fill in the team's own scoring templates (UPD, SC, DPG) for one question at a time. | One AI agent. **The template's own formulas** turn its inputs into points. Code refuses anything that breaks the rules. | People fill their own copy of the same templates. The app compares the two, for the "golden" cities. |

The AI never decides alone. Code does the checks that must be reliable (links, quotes, cut-off date, allowed scores). The prompts ask for the rest. The **coverage table** in section 3 shows which is which, rule by rule.

*Illustration only, not real data.* A Step 2 answer is one line in a fixed shape: `ANSWER: <direct answer> | EVIDENCE: <each law checked, with section> | CAVEATS: <exceptions> | PERIOD: <version or year> | LIMITS: <gaps>` [V].

---

## 2. One entry per prompt, in the order they run

There are 12 prompt files. Entries 1 and 2 are sent with every task; entries 3 to 12 are the task prompts. Helper files (skills, tools, agent files, categories, memory, original team prompts) are in section 2b.

### 1. Rules for every parastatal task (`prompts/shared-rules.md`) [V]
- **For:** the rulebook every agent reads before its own task, in all three steps.
- **Runs:** with every AI call for the Parastatal category.
- **Looks at / Produces:** nothing; it is text only, and it shapes every other prompt.
- **Rules it enforces:**
  - An empty field with a reason is correct; a plausible guess is a defect. Never invent, rebuild or "fix" a link; use only links a tool returned.
  - "Verified" means a person can open the page and read it. Pages that show only a record (metadata) are not verified.
  - Only government sites, the agency's own proven official site, and PRS (secondary). Wikipedia, news, blogs, Indian Kanoon, aggregators and memory are never cited.
  - The question's Detailed Methodology is the rule. If a skill or note disagrees, follow the methodology and write a `CONFIRM:` note.
  - For Law/Policy questions use only what was in force on the cut-off (31 Aug 2026); a Bill or draft is not law in force. "The law" means the whole stack (Act, Rules, regulations, notifications, other laws, city law).
- **Does NOT cover:** how to answer or score. The task prompts do that.
- **Known gaps:** the date "31 Aug 2026" is typed into this text, while the real setting lives in `categories/parastatal.md`; changing one does not change the other [V]. Parastatal only.

### 2. Rules for every city (ULG) task (`prompts/shared-rules-city.md`) [V]
- **For:** the same rulebook for the city-government category.
- **Runs:** with every AI call for the ULG category.
- **Looks at / Produces:** text only; nothing.
- **Rules it enforces:** the same URL, "verified", allowed-sources and "methodology is the rule" rules as entry 1, with the source priority "city government or state department first". Cut-off applies only "when the task names one". "The law" means the Act, the Rules, development control regulations, and the other body's law (for example the Town and Country Planning Act).
- **Does NOT cover:** answering or scoring.
- **Known gaps:** the ULG category sets no cut-off date today, so the cut-off paragraph does nothing there [V].

### 3. Find the parastatals of a city (`prompts/discover-parastatals.md`) [V]
- **For:** finding which agencies serve a city and judging if each counts as a parastatal.
- **Runs:** once per city, in Step 1. Skipped on a repeat run if the Sources workbook already lists parastatals, unless "Full refresh" is chosen. Not used for ULG [V].
- **Looks at:** the web (up to 8 searches and 8 page opens, no domain limit); the team's register list; team notes (screening list, scope decisions).
- **Produces:** a list of parastatals marked "eligible" or "needs review", with type, revenue and capital-works flags, evidence links, and a note on who delivers each of the three functions.
- **Rules it enforces:**
  - Only three kinds count: planning/development authorities, water and sewerage, public transport.
  - Six tests, E1 to E6 (function, not the city government, not a state department, not an excluded type, constituted and working today, covers the city).
  - Housing boards, roads agencies, power utilities, Smart City companies and environment bodies are excluded.
  - "When in doubt, needs review." Names in the team's notes are candidates, never pre-approved.
- **Does NOT cover:** researching an agency in depth, or finding its documents.
- **Known gaps:** the original team prompt has a seventh test (E7, a verified source for the legal basis); this one stops at E6 [V]. The "COVERAGE:" note is free text that no code reads [V]. Surat has no agreed screening list [V].

### 4. Profile one parastatal (`prompts/parastatal-profile.md`) [V]
- **For:** establishing the facts about one agency: its Act, whether it is still active, who holds executive power, whether it has a budget, and its official website.
- **Runs:** once per parastatal, in Step 1, in parallel.
- **Looks at:** the web (8 and 8, no domain limit); team notes.
- **Produces:** the governing Act (with "[unverified]" on anything not seen in a fetched text), status, chief-executive and budget flags, candidate websites, and notes in four parts: INSTRUMENTS, EXEC, DOMAINS, CONFIRM. Code then scores each candidate website from 0 to 100.
- **Rules it enforces:**
  - Record where a provision is, never whether it earns credit.
  - Find the executive authority by what the post does, not its title.
  - Never list Wikipedia, directories or social media as the website.
  - Try to open a government page that links to the agency's site.
- **Does NOT cover:** answering or scoring; building the source list.
- **Known gaps:** none found beyond entry 1's.

### 5. Profile the city government (`prompts/city-profile.md`) [V]
- **For:** the same job for the city government (ULG): its Act, name, whether it was renamed or merged, the bodies that share planning, its website.
- **Runs:** once per city, in Step 1, ULG category only.
- **Looks at / Produces:** like entry 4, plus a "PLANNING BODIES" note (location only, no verdicts).
- **Rules it enforces:** the same website and "[unverified]" rules; no Wikipedia or directories.
- **Does NOT cover:** answering or scoring.
- **Known gaps:** the file's first line says `TASK: parastatal_profile`, copied from entry 4; it looks harmless [A].

### 6. Find sources for one parastatal (`prompts/find-sources.md`) [V]
- **For:** building the Citation Sheet: the official documents a researcher needs to answer the listed questions.
- **Runs:** once per parastatal in Step 1 (a second, targeted search for questions still without a verified source), plus once per city for "shared laws only" when two or more parastatals are researched.
- **Looks at:** a digest of the questions (ID, level, text, evidence requirement; **not** the methodology); the parastatal's website; the web, limited to gov.in, nic.in, prsindia.org and the agency's own domain (5 searches and 5 opens, unless a setting changes it) [V].
- **Produces:** candidate sources with title, link, type, a "useful for" line starting with a tag such as [ACT] or [RULES], and the question IDs; plus notes GAPS, TEAM-LEAD, CHECK. Code then opens every link.
- **Rules it enforces:**
  - Spend searches in a set order: Act and Rules first, then city and planning laws, then budget and reports.
  - One best source per tag. Never pad the list.
  - A team lead on a blocked site must be replaced by the official copy.
  - Never judge a question here; location notes only.
- **Does NOT cover:** judging a source's quality, or answering.
- **Known gaps:** it is not told the cut-off date or asked for the version in force on that day, apart from entry 1 [V].

### 7. Find sources for one city (`prompts/find-city-sources.md`) [V]
- **For:** the same Citation Sheet job for the ULG: state planning and municipal Acts, master plans, notifications, official pages.
- **Runs:** once per city, in Step 1, ULG category.
- **Looks at:** questions digest; the web limited to gov.in, nic.in, prsindia.org and the city government's own site.
- **Produces:** candidate sources and notes, as in entry 6.
- **Rules it enforces:** read the whole legal stack (each Act, then its Rules and notifications); search only the city's state; prefer the specific document over a home page; fewer, better sources.
- **Does NOT cover:** judging sources or answering.
- **Known gaps:** first line says `TASK: find_sources` (same name as entry 6); it looks harmless [A].

### 8. Judge one source (`prompts/assess-source.md`) [V]
- **For:** reading one link that opened successfully and deciding if it really supports what it was listed for.
- **Runs:** once per link in Step 1, including links the team added. In Step 2 the app only re-opens a team-added link; it does not run this agent [V].
- **Looks at:** at most 15,000 characters of the page text, picked for relevance. It never sees the open web.
- **Produces:** useful yes/no, a corrected "useful for", a status ("Current / Historical / Transitional / unclear", with era and period), an **Authority Score** (0 to 10), notes, and, for laws and policies only, the **effective date** and the **form** (in force, bill, draft, unknown).
- **Rules it enforces:**
  - The source must be about this city and state.
  - A government domain alone is not a 10. A metadata-only India Code page is at most 1.
  - The effective date is when the text took effect or "amended up to"; never "last updated", a footer date or the date we fetched it. A bare year counts as unknown.
  - A Bill or draft is never "in force".
- **Does NOT cover:** answering or scoring; whether the date is before the cut-off (code decides that).
- **Known gaps:** the prompt gives 9 to an agency's own site, but code caps every non-government address at 5 [V] (see section 4).

### 9. Answer one question for a parastatal (`prompts/answer-question.md`) [V]
- **For:** answering one question for one parastatal, using only the Citation Sheet.
- **Runs:** once per parastatal and question in Step 2, in parallel. Main (roll-up) questions are not answered by the AI; code adds up their sub-questions [V].
- **Looks at:** the question, its level, the **Detailed Methodology word for word**, the evidence requirement, up to 8 ranked sources (trimmed to fit), the section's guide (UPD, SC or DPG), and team notes. It may read more of a source or search the sheet (up to 8 tool calls). No web.
- **Produces:** sufficiency, an answer in the fixed shape, a proposed score (or blank), the Citation ID used, a verbatim quote, and notes starting "CLASS; CONFIDENCE; BAND".
- **Rules it enforces:**
  - Plan first: what exactly is tested, which bodies to read, what decides it, and the "trap" (the nearer, narrower question not to answer).
  - Read the whole law stack and both sides of any relationship with the city government. "may" is not "shall"; advisory is not approval.
  - A score of 0 needs proof of absence; otherwise "not found" and a blank score.
  - Pick a class (A1, A2, R, P, M); A2 is never High confidence.
- **Does NOT cover:** finding new sources; looking anything up.
- **Known gaps:** an A2 answer marked High is flagged but not changed, and a score of 0 without proof of absence is not checked at all (section 3) [V].

### 10. Answer one question for a city (`prompts/answer-city-question.md`) [V]
- **For:** the same job for the ULG, once per city.
- **Runs:** once per city and question, Step 2, ULG category.
- **Looks at / Produces:** as entry 9, with city wording (name the body that prepares or approves each plan; read every body's law).
- **Rules it enforces:** the same as entry 9.
- **Does NOT cover:** finding sources.
- **Known gaps:** the cut-off lines are in the text, but the ULG has no date set, so nothing is hidden [V].

### 11. Score one question (`prompts/score-question.md`) [V]
- **For:** filling the cells of the team's scoring template for one question and one parastatal (or city).
- **Runs:** once per question and unit in Step 3, after Step 2.
- **Looks at:** the question, methodology, input columns with allowed values, the Step 2 answer, the one citation it relied on, the IDs of other sources (up to 8 tool calls, no web). It does **not** receive team notes [V].
- **Produces:** a value for each input column, an optional score, the band used, one Citation ID, a verbatim quote, location in the document, comments, confidence. Code copies the document name and link itself.
- **Rules it enforces:**
  - Check the Step 2 answer against the source; do not just copy it. If the sheet does not decide an input, leave it blank. Never guess.
  - A "NO" that scores 0 needs proof of absence; web pages that could not be opened are a "verification limit", never a negative.
  - Give exactly one allowed value; if "ALLOWED SCORES" are listed, nothing is converted.
  - The methodology is the rule; name the band used.
- **Does NOT cover:** finding sources; the formulas (the template does those).
- **Known gaps:** rule 8 says to convert a band to the Max Score; rule 13 says nothing is converted. Rule 8 is for the older ULG path only, but the prompt does not say so [V].

### 12. Review the question bank (`prompts/bank-review.md`) [V]
- **For:** an optional check of the question bank for problems that would make answers unreliable.
- **Runs:** only when asked for (`--llm-bank-review`), at the initial checks.
- **Looks at:** the question rows.
- **Produces:** a list of issues (question ID, warning or error, message).
- **Rules it enforces:** report only concrete problems and name the question: scale above the maximum score, a level that does not match the question, sub-question totals that do not add up, missing methodology, duplicates.
- **Does NOT cover:** fixing the bank. The bank is never changed.
- **Known gaps:** none found. A separate code check (not AI) now finds placeholder methodologies and empty levels [V].

---

### 2b. Helper files that are sent with the prompts

| File(s) | What it is | Who gets it | Notes [V] |
|---|---|---|---|
| `skills/scoring-methodology.md` | Plain rules for applying the methodology, the two levels (Law/Policy, Implementation), blank-not-zero, scale rules | Answer writers and the scorer | Says the methodology wins; says conversion of bands applies only on the older workbook path |
| `skills/sections/upd.md`, `sc.md`, `dpg.md` | One guide per question-bank section (planning; state capacities; participatory governance) | The Step 2 answer writer for that section | Each says "help only; the methodology wins". `skills/sections/ulg/upd.md` is the ULG's UPD guide |
| `skills/government-websites.md`, `skills/india-code-and-acts.md` | How to find official Indian sources; how to read Acts and India Code | Discovery, profile, source finders, judge, answer writers | India Code record pages are not the text of an Act |
| `agents/*.md` (10) | One file per agent: which prompt, skills, tools, model, effort | The app (settings) | Most search limits and the "no web in Steps 2 and 3" rule come from here |
| `tools/*.md` (6) | What each tool is, in the words the AI sees | The AI | `check_link`, `lookup_question`, `read_citation`, `search_citation_sheet`, `web_search`, `web_fetch` |
| `categories/parastatal.md`, `ulg.md` | Settings per category: question bank, templates, cut-off date, which agent does each job | The app | Parastatal sets `law_cutoff: 2026-08-31` and `undated_law_policy: confirm`. The ULG sets neither |
| `memory/` (general, city, category notes) | Team notes: where to look, local terms, screening lists | Steps 1 and 2 only, never Step 3 | Guidance, not evidence. Every answer lists the notes it used |
| `docs/source_prompts/` (3 files) | The team's original Phase 1 and Phase 2 prompts the app's prompts came from | Nobody: the app does not read them | History only. They allow external sources and "current consolidated text", which the app now does not |

---

## 3. Coverage table: which rules the code enforces

**ENFORCED IN CODE** = the app checks it. The AI cannot get round it. **ONLY IN A PROMPT** = the AI is asked, but nothing checks; it could ignore it. **NOT COVERED** = no prompt or code handles it. Where a rule has a reliable part and an unreliable part, it is split into two rows.

| # | Rule | Handled by | Status | Comment |
|---|---|---|---|---|
| 1a | The question's Detailed Methodology is sent to the model unchanged | Step 2 `base.py` (question block); Step 3 `template_scoring.py` (build prompt) | **ENFORCED IN CODE** | Tests check it word for word in both steps [V] |
| 1b | Step 3 points must be one of the levels the methodology lists | `score_levels.py`, `template_scoring.py` | **ENFORCED IN CODE** | A score not on the list is dropped and the row left for a person. Applies to typed-points questions; calculated questions use the template's formulas [V] |
| 1c | The AI reads the methodology correctly (right band, right part) | Prompts, skills (`CONFIRM:` on conflict) | **ONLY IN A PROMPT** | Code flags only a clear BAND mismatch (a number that is not a level) with a `CONFIRM:` note; it changes nothing [V] |
| 1d | A methodology that is only a note (DPG 4) is not answered | `methodology.py`, Step 2 `base.py`, initial checks | **ENFORCED IN CODE** | Step 2 writes "NO RULE:", leaves the row for a person and makes no model call. The initial checks warn the team. Step 3 has no separate check for it [V] |
| 2a | Law/Policy questions never see sources dated after 31 Aug 2026 | `cutoff.py`, Step 2 and Step 3 | **ENFORCED IN CODE** | Depends on the Citation Sheet's two date columns. Old rows without them are read from the status text; undated ones are used with a `CONFIRM:` note and Confidence at most Medium (setting `undated_law_policy: confirm`) [V] |
| 2b | The AI uses the version in force on that date and says which | Prompts | **ONLY IN A PROMPT** | Code checks only that the answer's own `PERIOD:` has no date after the cut-off [V] |
| 2c | The cut-off applies to ULG questions | Category settings | **NOT COVERED** | The ULG file sets no date, so nothing is applied [V]. The rule as you wrote it is for Parastatal only |
| 3 | A Bill or draft is not law in force | Judge prompt gives the "form"; `cutoff.py` hides "Bill-draft" sources from Law/Policy questions | **ENFORCED IN CODE** | The label comes from the AI's reading (or text for old rows). Implementation questions may still use them. Old Bengaluru answers (made before this rule) cite 17 Bills [V: checked 11 Nov] |
| 4 | Only .gov.in and .nic.in sources | Step 1 finder's search and page-open tools are limited to those domains plus prsindia.org and the agency's own site | **ENFORCED IN CODE** (by tool settings) | **The rule differs.** The real rule is wider: government domains, the agency's own site if proved official, and PRS (secondary). The code also counts ".gov" and ".kar.nic.in" as official. It does not filter links the team adds or old rows [V] |
| 4b | Non-government sources get a low authority score | `common.py` | **ENFORCED IN CODE** | Any source outside gov.in and nic.in is capped at Authority 5. This includes an agency's own proven site, which the prompt would rate 9 [V] |
| 5a | Wikipedia, news, blogs, aggregators, Indian Kanoon and similar are never cited | Step 1 finder's domain limits; prompts | **ENFORCED IN CODE** for the AI's search | The same tool limit applies. Discovery and profile agents have no domain limit [V] |
| 5b | Same, for links the team adds, and old sheets | none | **NOT COVERED** | No code rejects a blocked domain. A verified team link on such a site could be used in Step 2 [V] |
| 5c | Candidate websites on known non-official hosts score 0 | `links/trust.py` | **ENFORCED IN CODE** | A short list only: Wikipedia, business directories, social media, blog hosts. News sites, Indian Kanoon, FAOLEX and file-sharing are not on it [V] |
| 6 | Quotes are word for word | Step 2 `base.py`; Step 3 `check_reply_evidence` | **ENFORCED IN CODE** | Case and spacing are ignored. Only the quoted passage is checked, not the rest of the answer [V] |
| 7a | Never invent a URL | `llm.py` (URL must be returned by a tool), `final_qa.py`, `check_link` | **ENFORCED IN CODE** | An unreturned URL is discarded and Final QA flags it [V] |
| 7b | Never invent a GO number or a date in the answer text | Prompts | **ONLY IN A PROMPT** | Nothing compares them to the source, apart from the quote and the cut-off date check on PERIOD [V] |
| 8 | A2 answers never get High confidence | `answer-question.md`; `parse_class_line` | **ONLY IN A PROMPT** | Code adds a note "Class A2 is never High confidence. Check the Confidence." and leaves the value as written [V] |
| 9a | A blank score stays blank, never zero | `base.py`, `template_scoring.py` | **ENFORCED IN CODE** | No evidence gives a blank. Step 3 never writes partial inputs, so the template cannot show a calculated 0 [V] |
| 9b | A 0 needs proof that nothing exists | Prompts, skills | **ONLY IN A PROMPT** | A 0 from the AI is written if it is within range. Also, a main question sums only the sub-questions that have scores and says "Incomplete" in notes [V] |
| 10 | Each parastatal answered separately; the ULG once per city | `answers_master.py`, `sources_master.py` | **ENFORCED IN CODE** | One task per parastatal and question; each sees only its own sources plus the city's shared laws (by design). The ULG category has one unit per city [V] |
| 11 | Lucknow coverage is checked | none | **NOT COVERED** | Lucknow is in the register (Uttar Pradesh) with no city-government name and no parastatals. No code or team note names it (only the original Phase 1 prompt, as an example). The register check only warns when the ULG name is blank. The discovery "COVERAGE:" note is free text [V] |
| 12 | Unresolved items say Pending fetch with a reason | `base.py`, `template_scoring.py` | **ENFORCED IN CODE** for one case | **The rule differs.** "PENDING FETCH:" appears only when every source is dated after the cut-off or is a Bill. Other gaps use other words: Insufficient Evidence, SCORE-BLANK, CONFIRM, VERIFICATION-LIMIT, RTI-TARGET [V] |
| 13 | Answers use only the Citation Sheet (no web) | Setup check in `agent_setup.py`; tools reach only given rows | **ENFORCED IN CODE** | The check refuses web tools on Step 2 and Step 3 agents [V] |

---

## 4. Where prompts disagree or are outdated

Facts only. Nothing here has been fixed.

1. **`prompts/score-question.md`, rule 8 versus rule 13.** Rule 8 says to convert a band to the Max Score (band × Max ÷ top band). Rule 13 says nothing is converted when "ALLOWED SCORES" are listed. In code, rule 8 fires only when the task has a "SCALE" line, which only the older ULG path sends [V]. The prompt itself does not say that.
2. **`agents/question-scorer.md` does not mention the templates.** It talks about "the scoring workbook". It does not name the UPD, SC and DPG templates, the allowed-scores rule, or the years rule [V].
3. **`categories/ulg.md` points to the old workbook.** It names `ASICS_2027_UPD_Scoring_Workbook_v2.xlsx` (sheet "UPD Questions_290926 "), covers only the UPD section, and says SC and DPG "will be added". It has no `scoring_templates`, so ULG Step 3 uses the older path [V].
4. **Stale or unfinished memory notes.**
   - `memory/categories/parastatal/bengaluru-agencies.md` talks about an "Approach-Draft-based run" and says BMRCL "still needs team confirmation". The register has only 3 Bengaluru parastatals [V].
   - `memory/cities/surat.md` and `surat-agencies.md` are marked DRAFT, "Nothing below is evidence", and end with "TEAM TODO" [V].
   - `memory/cities/bengaluru.md` lists two conflicting effective dates and tells the AI to reuse neither [V].
   - Memory reaches Steps 1 and 2 only. Neither Step 3 path passes it [V].
   - Whether the facts in these notes are still true: [A].
5. **`agents/parastatal-discovery.md` lists "metro rail, housing, slum boards…"** as things it finds. The prompt excludes housing boards, and does not name slum boards [V].
6. **`agents/source-assessor.md` says it also runs "when Step 2 checks sources the team added".** In code, Step 2 only re-opens those links; the assessor does not run [V].
7. **The cut-off date is typed in two places.** `shared-rules.md` says "31 Aug 2026 for Parastatal"; the real setting is `law_cutoff` in `categories/parastatal.md` [V].
8. **Authority 9 versus code cap 5.** `assess-source.md` gives 9 to an agency's own official site page. Code caps every non-gov.in, non-nic.in address at 5, because no caller tells it the agency's own domain is official [V].
9. **`.gov` and `.kar.nic.in`.** Code treats these as official as well as gov.in and nic.in. No prompt mentions them [V].
10. **Discovery has E1 to E6; the original Phase 1 prompt has E7.** E7 (a verified source with Authority at least 6 that establishes the legal basis) is not in `discover-parastatals.md` [V].
11. **The original team prompts say the opposite on two points.** `docs/source_prompts/ASICS_Phase2_Prompt_v2.md` allows external sources ("Answered — External Source") and says "use the current consolidated text". The app answers only from the Citation Sheet and uses the cut-off version [V]. Nothing in the code reads these files [V].
12. **`phase2_citations_and_answers.md`** is a one-off Bengaluru fix prompt that refers to a "Parastatal Scoring - Bengaluru" sheet. That sheet is not in the app's workbooks [A].
13. **City prompts reuse parastatal task names** in their first line (`city-profile.md`: `parastatal_profile`; `find-city-sources.md`: `find_sources`) [V]. The effect is [A]: probably none.

---

## 5. Glossary

| Term | Plain meaning |
|---|---|
| **Prompt** | A written instruction for the AI. |
| **Agent** | One AI worker with one job, its own prompt, skills, tools and settings. |
| **Skill** | A help note an agent reads first (for example, how to read Indian Acts). |
| **Memory note / team context** | A note from the research team (for example, "ignore the old website"). Guidance, never evidence. |
| **Parastatal** | An agency created by government that is separate from the city government: a water board, a bus company, a development authority. |
| **ULG** | Urban Local Government: the city's own government (for example, a municipal corporation). Answered once per city. |
| **Citation Sheet** | The list of official sources found for a parastatal (or a city). Answers may use only the rows marked "Use for Answers? = Yes". |
| **Citation ID** | A short code for one row, such as `BWSSB-07`. |
| **Verified** | The exact link was opened and a person could read the real page. A record page with only a title and number is not verified. |
| **Authority Score** | 0 to 10: how strong a source is. A government address alone is not a 10. It is not the ASICS score. |
| **Class (A1, A2, R, P, M)** | Where an answer lives. A1: one clear public source. A2: secondary source or several instruments read together. R: held by an authority; needs an RTI request. P: behind a paywall. M: needs fieldwork. |
| **Confidence** | High, Medium or Low: how good the evidence is, not how sure the AI feels. A2 is never High. |
| **Methodology (Detailed Methodology)** | The question's own scoring rule. It is the rule; skills and notes are only help. |
| **Assessment level** | Law/Policy (what the law says) or Implementation (what happens in practice). |
| **Cut-off** | 31 Aug 2026. A Law/Policy question may use only text that took effect on or before it. |
| **Effective date** | When the cited text took effect, or "amended up to". Never the web page's "last updated" and never the day we fetched it. |
| **Bill** | A proposed law not yet passed and in force. It is not law in force. |
| **CONFIRM** | A note for a person: "check this". The AI writes it when it doubts or sources disagree. |
| **Pending fetch** | Every source for a Law/Policy question is later than the cut-off or a Bill, so the right version must be fetched. The answer says `PENDING FETCH:` and why. |
| **Golden city** | A city where people also fill the templates, so the app can compare people and AI. Choosing them is not built yet. |
| **Fingerprint** | A short code that changes whenever a file's text changes. The app records one for the whole setup in each run. |

---

## Appendix for developers

Fingerprint = first 8 characters of the file's SHA-256 today. Date = last git commit date; "11 Nov (uncommitted)" means the file has edits not yet committed (last commit in brackets). The whole `agent_setup/` folder's fingerprint, as the app computes it, is `4f6085f90f32` [V].

| File | Fingerprint | Last change |
|---|---|---|
| `prompts/shared-rules.md` | d05c9488 | 11 Nov (uncommitted) (9 Oct) |
| `prompts/shared-rules-city.md` | 5ab62fef | 11 Nov (uncommitted) (9 Oct) |
| `prompts/discover-parastatals.md` | 74de84aa | 5 Nov |
| `prompts/parastatal-profile.md` | b0c2b58e | 11 Nov (uncommitted) (9 Oct) |
| `prompts/city-profile.md` | 439ed39c | 9 Oct |
| `prompts/find-sources.md` | 1488745f | 11 Nov (uncommitted) (14 Oct) |
| `prompts/find-city-sources.md` | eddba9c7 | 14 Oct |
| `prompts/assess-source.md` | cc4284a7 | 11 Nov (uncommitted) (9 Oct) |
| `prompts/answer-question.md` | f335e386 | 11 Nov (uncommitted) (30 Oct) |
| `prompts/answer-city-question.md` | 23d2d1f8 | 11 Nov (uncommitted) (30 Oct) |
| `prompts/score-question.md` | 8c02c0da | 11 Nov (uncommitted) (5 Nov) |
| `prompts/bank-review.md` | 1f110d2e | 7 Oct |
| `skills/scoring-methodology.md` | ee359cca | 11 Nov (uncommitted) (30 Oct) |
| `skills/sections/upd.md` | de937749 | 11 Nov (uncommitted) (9 Oct) |
| `skills/sections/sc.md` | 3b66dc58 | 11 Nov (uncommitted) (9 Oct) |
| `skills/sections/dpg.md` | e497e405 | 11 Nov (uncommitted) (9 Oct) |
| `skills/sections/ulg/upd.md` | 1d9a33ae | 30 Oct |
| `skills/government-websites.md` | f02c6ffa | 7 Oct |
| `skills/india-code-and-acts.md` | 52156e8e | 7 Oct |
| `agents/answer-writer.md` | 3d12d303 | 14 Oct |
| `agents/citation-builder.md` | 89f2a924 | 14 Oct |
| `agents/city-answer-writer.md` | 17c666c1 | 30 Oct |
| `agents/city-citation-builder.md` | 4ee1637b | 30 Oct |
| `agents/city-profiler.md` | 31f2daab | 30 Oct |
| `agents/parastatal-discovery.md` | 91381587 | 14 Oct |
| `agents/question-bank-reviewer.md` | de6315a4 | 14 Oct |
| `agents/question-scorer.md` | 59d71e4f | 14 Oct |
| `agents/source-assessor.md` | 9cf80441 | 14 Oct |
| `agents/website-profiler.md` | 4b64c906 | 14 Oct |
| `tools/check_link.md` | eae6dce7 | 7 Oct |
| `tools/lookup_question.md` | 1dd9d6bf | 7 Oct |
| `tools/read_citation.md` | 76abbf1b | 7 Oct |
| `tools/search_citation_sheet.md` | 4546f36c | 7 Oct |
| `tools/web_fetch.md` | 071e1bb0 | 14 Oct |
| `tools/web_search.md` | d2dbfd70 | 14 Oct |
| `categories/parastatal.md` | c47036fd | 11 Nov (uncommitted) (5 Nov) |
| `categories/ulg.md` | 1c637145 | 30 Oct |
| `memory/categories/parastatal/bengaluru-agencies.md` | 621479b8 | 30 Oct |
| `memory/categories/parastatal/scope-decisions.md` | 6d17fdd1 | 30 Oct |
| `memory/categories/parastatal/surat-agencies.md` | e642a7fc | 30 Oct |
| `memory/cities/bengaluru.md` | 39143b0a | 30 Oct |
| `memory/cities/surat.md` | 33643d68 | 9 Oct |
| `docs/source_prompts/ASICS_Phase1_Prompt_v2.md` | 24d51a89 | 9 Oct |
| `docs/source_prompts/ASICS_Phase2_Prompt_v2.md` | 6438cc07 | 30 Oct |
| `docs/source_prompts/phase2_citations_and_answers.md` | dd7ab390 | 7 Oct |

The `README.md` files in `agent_setup/` and its sub-folders are read by people only. The app never sends them to the AI, but they are part of the folder fingerprint [V].

**Where the prompt text is built (code):** `agent_setup.py` (order: shared rules, skills, task prompt), `llm.py` (team notes go at the top of the message; no notes for Step 3), `agents/sections/base.py` (Step 2 question block and checks), `scoring/template_scoring.py` (Step 3 prompt and checks), `agents/common.py` (source judge input, link vetting), `cutoff.py` and `methodology.py` (cut-off and methodology checks) [V].
