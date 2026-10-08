# ASICS Assessment

A tool for Janaagraha's **Annual Survey of India's City-Systems (ASICS)**. Every ASICS
**vertical** (Parastatal, UPD, and more to come) goes through the same three steps:

1. **Step 1: Find sources.** Give it a city. It works out what to assess (for Parastatal, the city's parastatals, found by the agent itself; for UPD, the city government), checks each one's official website, and builds a **Citation Sheet** of official sources for the question bank. **Your team then reviews the Sources workbook**: untick parastatals or sources, and add sources you know about.
2. **Step 2: Answer questions.** Every answer uses **only** the reviewed Citation Sheet and names the **Citation ID** it relies on. It includes a verbatim quote, where to find it, and a saved copy of the page.
3. **Step 3: Score.** Each answer is scored from its citation in the expert team's scoring workbook, by the AI and by interns, side by side.

Choose the vertical in the app's sidebar (**Vertical**). Each one has its own question bank,
agents, city folders and scoring workbook, set in `agent_setup/verticals/` (see
[Verticals](#verticals-parastatal-upd-and-new-ones)).

This README has two parts:

- **[For the research team](#for-the-research-team)**: using the app and reviewing results. No technical knowledge needed.
- **[For developers](#for-developers)**: setup, how it works, and how to extend it.

---

# For the research team

## Opening the app

Double-click **`Start ASICS.command`** (Mac) or **`Start ASICS.bat`** (Windows) in the project
folder. A black window opens, then the app opens in your web browser. **Keep the black window
open** while you work; close it when you're done.

> If you see "This computer isn't set up yet", ask your developer to follow
> [Setting up a new computer](#setting-up-a-new-computer).

The **Home** page shows the three steps and where each city is up to, for the vertical
chosen under **Vertical** at the bottom of the sidebar (the app remembers your choice). To learn the app, tick **Practice with sample data** on Step 1. It uses two made-up
cities, costs nothing, takes seconds, and shows every step.

## Running several verticals and steps at once

**Assess → Run steps** runs everything for your cities in one go. Choose:

- **Verticals**: e.g. Parastatal and UPD (every vertical in `agent_setup/verticals/` is listed).
- **Cities**: any cities in the city register.
- **Steps**: 1 Find sources, 2 Answer questions, 3 Score (any of them).

Each step runs for every chosen vertical before the next step starts: Step 1 for Parastatal,
Step 1 for UPD, then Step 2 for both, then Step 3 for both. The **Current run** page shows each
stage and its outcome.

Two review points, both on by default (under **Review and options**):

- **Pause after Step 1** so the team can review the Sources workbooks before anything is
  answered. When Step 1 is done, review each city's workbook in **City files** (choose its
  vertical in the sidebar), save it, then press **Continue to Step 2**.
- **In Step 1, review the parastatals found** before their sources are researched (Parastatal
  only).

A stage only does what's possible: Step 2 needs the city's Sources workbook, and Step 3 only
scores cities whose Step 2 is up to date. Cities that aren't ready are listed, not forced
through. The Step 1, 2 and 3 pages are still there for running one step of one vertical
with more options (sections, single questions, earlier workbooks).

## The city register

The list of cities is one Excel file, `data/cities/ASICS_Cities_and_Parastatals.xlsx`. Open it
from the app's **City register** page.

- **Cities sheet:** one row per city: City, State, and City government (ULG). That's all the tool needs.
- **Parastatals sheet (optional):** add a parastatal here only if you want to be sure the agent includes it. The agent finds the rest itself.
- **Don't add website links.** The tool finds and checks every link itself.
- **Other names (optional):** other spellings used in scoring workbooks, comma separated (e.g. `Bangalore` for Bengaluru), so scores match the right city.

After saving, press **Check again** on the City register page. Any mistakes are listed in
plain language, and a mistake in one city never stops the others.

## Step 1: Find parastatals and sources

> For a city-level vertical such as UPD there are no parastatals to find: Step 1 checks the
> city government's official website and builds the Citation Sheet straight away.

1. Open **Step 1 · Find sources** in the sidebar, pick the cities and sections, and press **Start Step 1**.
2. For each city the agent:
   - **Finds the parastatals.** It researches the state portal, the urban development department, the city government's site and official Acts, then adds the register's parastatals.
   - **Checks each parastatal's official website.** Every candidate website gets a score out of 100, with the reasons listed. See [How the official website is checked](#how-the-official-website-is-checked).
3. **Review screen, once for all cities.** You see each parastatal: why it was included, its website and score, the law that created it, and its status. Untick any you don't want researched, then press **Continue**. Unticked ones stay in the Sources workbook, marked *Include? = No*.
4. The agent **builds the Citation Sheet** for each parastatal. It searches for official sources for the questions, then runs a second, targeted search for any question still without a source. Every link is opened and checked.

The result is one **Sources workbook** per city, in **City files**:

| Sheet | What it's for |
|---|---|
| **How to Use** | Instructions |
| **Needs Attention** | Problems to check, in plain language |
| **Parastatals** | Every parastatal: **Include?** (Yes/No), Found By (Agent or Your team), website and **Website Check** score with reasons, Act, status, and the Yes/No facts that decide which questions apply |
| **Citation Sheet** | Every source, with a **Citation ID** (e.g. `BWSSB-07`), link, saved copy, what it's useful for, Verification Status, Authority Score, and **Use for Answers?** (Yes/No) |
| **Coverage** | Which questions have a source, and which have none yet |

## Reviewing the Sources workbook

Open it from **City files** with **Open the Sources workbook in Excel**. Then:

- **Parastatals:** set **Include?** to No to leave one out. To add one, add a row with its ID, name and Type, and leave Found By empty.
- **Citation Sheet:** open each link, or its saved copy, and set **Use for Answers?** to No for anything unsuitable. Links that failed the check start as No. To add a source, add a row with Parastatal (an ID from the Parastatals sheet, or `All parastatals`), Source Title, Official URL and What This Source Is Useful For. Leave Citation ID empty; it is filled in automatically. Your links are opened and checked the same way as the agent's.
- **Coverage:** questions marked *No source yet* will be answered *Insufficient Evidence* unless you add a source.
- **Your Notes** columns are never overwritten.

Save and close the file when you're done. You can run Step 1 again at any time, for example
to look for new sources. It keeps your decisions, your rows and your notes, and saves the
previous version in a `history` folder first.

### While it runs

The **Current run** page says **"Working, nothing for you to do right now"** while the agent
works. The **Right now** table shows what each parastatal is doing, for example *"Checking
links: 6 of 14 done"*, and when it last changed. Building the Citation Sheet takes several
minutes per parastatal, and up to 4 are worked on at once.

When the agent needs you, the page shows an **Action needed** banner with **Continue**
buttons. That's the only time you need to do anything.

If nothing has changed in the **Updated** column for more than 20 minutes, tell your
developer. Slow websites and slow research calls are stopped automatically (after 1 minute
and 15 minutes respectively) and reported in **Needs Attention**, so a run shouldn't get stuck.

## Step 2: Answer questions

Open **Step 2 · Answer questions** in the sidebar, pick the cities, and press **Start Step 2**. For each city you can
see how many parastatals and citations are ready.

- Answers use **only** Citation Sheet rows marked *Use for Answers? = Yes*. There is no other research.
- Each answer names its **Citation ID**, quotes the source word for word, and says **Where to Find It**.
- If nothing in the Citation Sheet answers a question, the answer is *Insufficient Evidence*, and **Source Needed** says what kind of document would answer it. Add one to the Citation Sheet and run Step 2 again.

Each Step 2 run creates a new **answers workbook** for the city, in **City files**.

## Viewing results in the portal

You don't need to open Excel just to look. On **Home**, press **View** on a city, or open
**City files**, for these tabs:

| Tab | What you see |
|---|---|
| **Overview** | Parastatals, citations ready, questions with a source, and a chart of answer status per parastatal |
| **Parastatals** | Each parastatal with its website, Website Check score, Act and status |
| **Citation Sheet** | Every source, searchable and filterable. Click one to see its notes and saved text. |
| **Coverage** | Which questions have a source, per parastatal |
| **Answers** | Choose a run, filter, and click a question to see the answer, citation, where to find it, and the **quote highlighted in the saved source** |
| **Files** | Open or download the workbooks |

**Re-check links** shows its results on screen too, including earlier re-checks. The portal
only shows what's in the workbooks; to change anything, open the workbook in Excel.

## Reviewing the answers

| Sheet | What it's for |
|---|---|
| **How to Review** | Instructions, plus what every Status means |
| **Needs Attention** | Problems to fix, in plain language; *Must fix* items first |
| **Citation Sheet** | The list the answers were allowed to use |
| **Parastatal Scoring - &lt;City&gt;** (or **Scoring - &lt;City&gt;** for long names) | One row per parastatal and question |
| Technical Log | For your developer; ignore it |

For each answer:

1. **Citation ID** tells you which Citation Sheet row it relies on. Click the **Citation URL**.
2. Read **Where to Find It**, for example *"Page 12 of the PDF, under the heading 'Section 16. Plans'"*.
3. Press **Ctrl+F** (Windows) or **Cmd+F** (Mac) and paste the **Search Phrase** to find the **Evidence Excerpt**.
4. If the page has changed, click **Open saved copy**.
5. Choose **Agree**, **Disagree** or **Needs change** in **Reviewer Decision**, and add a comment.

Rows are coloured: **green** is answered, **amber** needs a person to look, **red** means no evidence, and **grey** is not applicable.

## How the official website is checked

Each candidate website is opened and scored. The Website Check column lists every point:

| Signal | Points |
|---|---|
| Government web address (gov.in / nic.in) | +40 |
| Linked from other government websites | +20 for one, +30 for two or more |
| Opens properly and shows real content | +10 |
| Says it is run by the government, or is hosted by NIC | +10 |
| Lists a government email address (also written as `name[at]dept[dot]gov[dot]in`) | +10 |
| Has Right to Information (RTI) / PIO details | +5 |
| Its social media account is also linked from a government page | +5 |
| Its name or short name is in the web address or page title | +5 |
| A directory, Wikipedia, blog or social media page | always 0 |

**70+ = Official. 50–69 = Probably official**: used, but flagged for you to confirm. **Below 50
= Not confirmed**: not used as the official website, but sources are still researched from
other official sites. A website that doesn't open scores at most 49, but a gov.in / nic.in
address with the parastatal's own name is still treated as **Probably official**, and flagged
for you to open and confirm (many government sites are slow or don't open in the automatic
check).

## How links are checked

1. **Only links found by a web search, or added by your team, are used.** A link the AI writes from memory or pieces together is thrown away.
2. **Each exact link is opened separately**, the way a browser would, without changing it. It must show real, readable content. An error page, a login or captcha page, a data feed, or an India Code page showing only a summary of an Act doesn't count.
3. **Anything uncertain goes to a person.** Pages that need JavaScript, scanned PDFs and links that jump to another website are marked *Human Verification Required*, scored 0, and start as *Use for Answers? = No*.
4. **A copy of every page that passes is saved**, and every quote is matched against it word for word.

## Giving the agents more context (Team memory)

Some things the agents can't find on the web: where a parastatal hides its budget, a recent
renaming, a local term, a website to ignore. Add these as **notes** on the app's **Agent
setup** page (Team memory tab), or as `.md` files in `agent_setup/memory/`:

- **General:** used in every run.
- **One city:** used only when that city runs.
- **One vertical:** used only for that ASICS vertical. The current one is **parastatal**; add a new vertical (e.g. Mobility) when that work starts.

You can narrow a note to some parastatals, sections, agents or steps. Notes are **guidance,
not evidence**: answers still quote the Citation Sheet, and each answer lists the notes it used
in **Team Context Used**. Saving keeps the previous version, and archiving removes a note from
use without deleting it. The **Preview** tab shows exactly which notes an agent would receive.

## Checking links again later

Open **Re-check links**, pick a Sources or answers workbook, and press **Re-check now**. You get
a copy with **Link Still Opens?** and **Quote Still on Page?** columns. Your original is not
changed.

## Step 3: Score

Step 3 comes **after Step 2**. A city can be scored only once Step 2 has answered it, and only
while its Sources workbook hasn't changed since. If it has, run Step 2 again first. The
**Step 3 · Score** page shows which cities are ready.

**Evidence comes only from Steps 1 and 2.** Each question is scored from its Step 2 answer and
the reviewed Citation Sheet; the AI does no web research in Step 3. Checked in code:

- The AI must name the **Citation ID** its score rests on: a reviewed, verified Citation Sheet
  row for that agency.
- Its **quote** must appear word for word in that source's saved text. If not, its inputs are
  discarded and the row is left for a person.
- The **document name and link** in the scoring workbook are copied from the Citation Sheet,
  never written by the AI. The page number comes from where the quote was found.
- Where Step 2 found **no evidence**, the AI isn't asked. The row is left for a person, with
  the kind of source that is missing.

Scores are kept in Excel, in the expert team's scoring workbooks: one per vertical, all with
the same layout. The workbook's own formulas turn the inputs into points, roll sub-questions
up to main questions, and main questions up to the overall score. The AI and people fill in
the **same cells** in separate copies, so their scores are directly comparable. People's
scores are the golden dataset for checking the AI.

Step 3 works the same for every vertical: it scores from that vertical's own Step 2 answers
and Citation Sheet. For Parastatal the scoring workbook has one row per city and agency; for
UPD, one row per city.

### On the Step 3 · Score page

**AI scoring:** choose cities that are ready (and, to try it out, a few questions), then
**Start Step 3**. It runs in the background; you can leave the page. A city counts as
**Scored** on Home after a run over all questions. Try **Practice with sample data** first:
it uses the practice cities, so run a practice Step 1 and Step 2 before it.

**The one workbook to use** is the vertical's scoring workbook, `scoring/2027/ai/<CODE>_ai.xlsx`
(e.g. `PARASTATAL_ai.xlsx`), shown first when Step 3 finishes, with **Open** and
**Download**. Start from its first sheet, **Scores (start here)**: one row per question and
agency (or city).

| Columns | What they are |
|---|---|
| Question, Row, Question text | what is being scored, and for whom |
| AI score, Max score | the points the workbook's formulas give for the AI's inputs |
| **★ Your score, ★ Your comments** (yellow) | your own score where you check or disagree; kept when the AI scores again |
| Agrees with AI? | Yes / No (red) once you've entered a score |
| Status | *Scored by AI*, or *Left for a person* (orange): filter on it to see what's left |
| Step 2 status, Step 2 answer, Citation, Link, Quote | the evidence the score rests on |
| AI's reasoning, Why left for a person | the AI's explanation, or why it didn't score |

The other sheets are the experts' scoring workbook itself (one per question, plus the summary
that adds the scores up), which the formulas use. The page also previews the Scores sheet
(**See the scores here**). Other files (all cities side by side; a technical log) are under
**Other files**.

**People's scoring (interns, in the experts' full workbook):**

1. **Open the assignments workbook.** One row per intern and set of questions: Vertical,
   Intern, Questions (`UPD1a, UPD1b`, or `UPD1*` for UPD1 and its parts), Cities (names, or
   `All`). To split a question, give two interns the same question with different cities.
2. **Make interns' copies.** Each intern gets a file with their rows highlighted in yellow
   and other questions hidden. For Parastatal, only cities Step 2 has answered are included.
   A **Step 2 evidence** sheet lists, for every row, the Step 2 status, Citation ID, source,
   link and quote. Existing copies are never replaced.
3. Interns fill in their copies in Excel: the input the row above each column asks for
   (e.g. YES / NO), the evidence and comments.
4. **Merge and calculate** (as often as you like). Only what interns typed is copied, never
   formulas. Two interns giving different answers for the same cell, or an answer that isn't
   allowed (e.g. "maybe" where YES / NO is asked), are listed under **Needs a look**.

The **Scores** page (under Results) shows city scores from people and the AI side by side,
every question's score, and **Only where people and AI differ**. It is view only; scores are
changed in Excel.

A city's vertical score is its overall score in that workbook; for Parastatal it is the
average of the city's agencies. The ASICS score is the average of the verticals (equal
weights). "?" means nothing is scored yet; yellow cells in Excel are provisional.

Everything lives in `scoring/2027/`:

| Folder | What's in it |
|---|---|
| `templates/` | the experts' scoring workbooks, one per vertical |
| `assignments/` | `ASICS_2027_Scoring_Assignments.xlsx`: which intern scores which questions for which cities |
| `human/` | one copy per intern per vertical (interns work only in their own copy) |
| `merged/` | everyone's work put together and calculated, with a **Merge report** sheet |
| `ai/` | the AI's copy, and `runs/` with a log of every row (Step 2 status, citation, quote, why) |
| `results/` | `ASICS_2027_Scores.xlsx`: city × vertical scores from people and the AI, and the ASICS score |
| `evals/` | how closely the AI agrees with people, after each AI run |

**Calculating needs LibreOffice** (free, from libreoffice.org). It runs in the background;
nobody needs to open it. **Check workbooks** lists anything that would stop scores adding
up: a sheet whose name and code differ, missing columns, cities that don't match the city
register.

### The Parastatal scoring workbook (draft)

`templates/ASICS_2027_Parastatal_Scoring_Workbook_DRAFT.xlsx` was generated from the
methodology sheet in the UPD layout: one sheet per question, one row per city and agency
(`Bengaluru – BWSSB`), an **Applies?** column from the question's Applicability and the
agency's type, and summary and city sheets with the same roll-up formulas as UPD. Each
question has a simple input (a score, or one per "Part A/B" where the methodology splits the
points) for the experts to replace with their own. Its first sheet lists what to check. To
regenerate it (e.g. after Step 1 finds more agencies):

```bash
uv run python scripts/make_scoring_skeleton.py
```

---

# For developers

## Setting up a new computer

1. Install [uv](https://docs.astral.sh/uv/). On a Mac: `brew install uv`.
2. In the project folder:

   ```bash
   uv sync
   ```

   ```bash
   cp .env.example .env
   ```

   Then set `ANTHROPIC_API_KEY` in `.env`.
3. Run the tests (offline, free):

   ```bash
   uv run pytest
   ```

4. Double-click `Start ASICS.command` to test the launcher. The first time, macOS may need right-click → **Open**.

The app only accepts connections from this computer (`.streamlit/config.toml`), because it
uses the API key.

## Other ways to run it

The app directly:

```bash
uv run streamlit run app.py
```

Step 1 for a city from the terminal (repeat `--city`, or use `--all-cities`):

```bash
uv run python scripts/run_pipeline.py --step sources --city Bengaluru
```

Step 2 from the terminal:

```bash
uv run python scripts/run_pipeline.py --step answers --city Bengaluru --pillar DPG
```

A free check of the question bank and register for every city:

```bash
uv run python scripts/run_pipeline.py --step sources --all-cities --checks-only
```

Re-check a workbook's links:

```bash
uv run python scripts/recheck_links.py "outputs/cities/Bengaluru/ASICS_Bengaluru_Sources.xlsx"
```

LangGraph Studio, with graphs `step1_sources` and `step2_answers`:

```bash
uv run langgraph dev
```

## How it works

```mermaid
flowchart TD
    subgraph S1["Step 1: sources_master.py"]
        IC1[initial_checks] --> PD[parastatal_discovery<br/><i>discover → profile × parastatal<br/>(website trust check)</i>]
        PD --> CS{{confirm_scope<br/><i>human review</i>}}
        CS --> LA[links_agent × parastatal<br/><i>re-test → research → fill gaps</i>]
        LA --> FS[finalize_sources<br/><i>QA · Sources workbook</i>]
    end
    FS --> SW[(Sources workbook<br/>reviewed and edited by the team)]
    SW --> IC2
    subgraph S2["Step 2: answers_master.py"]
        IC2[initial_checks] --> PC[prepare_citations<br/><i>check team-added rows</i>]
        PC --> ANS[answer_UPD / answer_DPG / answer_SC / answer_GENERIC<br/><i>× parastatal × question, Citation Sheet only</i>]
        ANS --> FA[finalize_answers<br/><i>roll-ups · QA · answers workbook</i>]
    end
```

- **Two master agents,** [agents/sources_master.py](src/asics_agent/agents/sources_master.py) and [agents/answers_master.py](src/asics_agent/agents/answers_master.py), handle one city each and route between phases with plain Python.
- **The Excel handoff** is [sources_workbook.py](src/asics_agent/sources_workbook.py). It reads, writes and merges the Sources workbook, keeping the team's decisions, rows, notes and Citation IDs across re-runs.
- **Several cities** run through `BatchRun` in [runner.py](src/asics_agent/runner.py), one after another. Step 1 has a single review for all cities, and the app and CLI both use it.
- **Files** go to `outputs/cities/<City>/`: the Sources workbook, `evidence/` (saved copies and text, shared by both steps), `history/`, `answers/<run>/` and `checks/`. Batch indexes go to `outputs/batches/<id>/`.

| Sub-agent | File | What it does |
|---|---|---|
| Initial checks | [initial_checks.py](src/asics_agent/agents/initial_checks.py) | Loads the question bank, the register and the city's Sources workbook |
| Parastatal discovery | [parastatal_discovery.py](src/asics_agent/agents/parastatal_discovery.py) | Finds parastatals (merged with the team's), profiles each in parallel, rates candidate websites |
| Website trust check | [links/trust.py](src/asics_agent/links/trust.py) | The scoring table above, computed in code from the page, the fetched government pages ("backlinks") and the access check |
| Links agent | [links_builder.py](src/asics_agent/agents/links_builder.py) | Re-tests earlier rows, researches sources, then a gap-filling pass for uncovered questions |
| Section answer agents | [sections/](src/asics_agent/agents/sections/) | Answer from the Citation Sheet only, citing a Citation ID; the quote is verified against the saved page |
| Roll-up + final QA | [rollup.py](src/asics_agent/agents/rollup.py), [final_qa.py](src/asics_agent/agents/final_qa.py) | Sum MQs where the methodology says so; `qa_sources` / `qa_answers` checklists |

### Agents, prompts, skills and memory: `agent_setup/`

Everything the model is told lives in [agent_setup/](agent_setup/), described in
[agent_setup/README.md](agent_setup/README.md). [agent_setup.py](src/asics_agent/agent_setup.py)
reads it:

- `call_json(services, "<agent>", …)` in [llm.py](src/asics_agent/llm.py) loads `agent_setup/agents/<agent>.md` and builds the system prompt (shared rules + skills + task prompt). It binds web tools only if `web_research: true`, and passes the agent's `effort`.
- Memory notes matching the call's `MemoryScope` (city, parastatals, sections, agent, step) are added at the top of the message; `scope.used` records them. The size limit is `ASICS_MEMORY_MAX_CHARS`, with the most specific notes kept first.
- Initial checks validate the folder (missing prompts or skills, broken settings blocks, notes for unknown cities). Each run's summary records `agent_setup_fingerprint`.

### Configuring LangGraph

**Graphs.** Two graphs are registered in `langgraph.json`: `step1_sources` and `step2_answers`.
Open them with `uv run langgraph dev`; LangGraph Studio shows every node, sub-graph and
parallel branch. Each graph is a `StateGraph` over `MasterState`
([agents/state.py](src/asics_agent/agents/state.py)), built by `build_sources_graph` and
`build_answers_graph`, using:

- sub-graphs as nodes: discovery, the links agent, one answer agent per section;
- `Send` to fan out per parastatal, and per parastatal × question;
- `interrupt()` for the review pause, with a checkpointer in [runner.py](src/asics_agent/runner.py);
- `stream_mode=["updates", "custom"]` for live progress.

**Run options (`context_schema`).** Both graphs declare
[`RunOptions`](src/asics_agent/run_options.py) as run context: `model`, `effort`,
`web_search_max_uses`, `max_tool_calls` and `memory_max_chars`.

- **Where to set them:** Studio shows them as a form per run. The CLI takes `--model`, `--effort`, `--web-searches` and `--max-tool-calls`. The app has **Advanced options** on the Start page.
- **Precedence:** a run's `effort`, `web_search_max_uses` and `max_tool_calls` override every agent's own setting. A run's `model` applies only to agents that don't name their own.
- **In code:** read them with `current_options()`.

**Agents and their tool loop.** Every model call goes through `call_json(services, "<agent>", …)`
in [llm.py](src/asics_agent/llm.py), which builds the agent from its file in
`agent_setup/agents/` and runs it as a small LangGraph graph:

```
model ──(our tool calls)──▶ tools (ToolNode) ──▶ model ──(final JSON)──▶ end
  ▲ └──(server tools paused the turn)──┘           └─▶ over_limit, after max_tool_calls
```

- **Server tools** (`web_search`, `web_fetch`) run inside the model call.
- **Our tools** run in LangGraph's `ToolNode`, so every call is a visible step in Studio, appears as live progress, and is listed in the Technical Log (and in an answer's Notes as "Looked further with: …").

**Adding a tool:**
1. Write `src/asics_agent/tools/<name>.py` with an `Args` Pydantic model and `register(ClientTool(name=…, args=Args, run=fn))`. `fn(ctx, **args) -> str` gets a `ToolContext` that holds only what that call may see: the run, the allowed URLs, and the Citation Sheet rows.
2. Write `agent_setup/tools/<name>.md`; its body is the description the model sees.
3. List it under an agent's `tools:`. The setup check catches unknown tools, bad options, both `allowed_domains` and `blocked_domains`, and web tools on Step 2 agents.

**Model per agent:** set `model:` in an agent's file; `Services.llm_for()` creates and reuses
one client per model.

### Where the rules are enforced

The original rules are in [docs/source_prompts/phase2_citations_and_answers.md](docs/source_prompts/phase2_citations_and_answers.md).
They're given to the model in [agent_setup/prompts/](agent_setup/prompts/) **and** enforced in code:

| Rule | Enforced by |
|---|---|
| A URL is used only if a tool returned it verbatim, or the team added it | [links/registry.py](src/asics_agent/links/registry.py); `qa_sources` |
| Human accessibility test, including India Code | [links/accessibility.py](src/asics_agent/links/accessibility.py) |
| Authority-score caps | [agents/common.py](src/asics_agent/agents/common.py): unverified sources get 0, non-government domains are capped at 5 |
| **Answers use only the Citation Sheet** | Step 2 agents can't have web tools (setup check); `answer_from_citations` and the `read_citation` / `search_citation_sheet` tools receive only in-use, verified rows; an answer citing any other ID becomes *Human Verification Required*; `qa_answers` re-checks |
| Links proposed by the citation builder were opened | `check_link` runs the same accessibility test during research, and refuses URLs no tool returned |
| Traceable quote | The quote must appear verbatim in the cited row's saved text; `locate_quote` finds its page and heading |
| Status and Notes on every row | `finalize` in `sections/base.py`; `qa_answers` |
| Preserve the workbook | [workbook.py](src/asics_agent/workbook.py) updates rows in place and never overwrites Reviewer or Your Notes columns |

The source prompt's "research an external source when the Citation Sheet is insufficient" is
now done **in Step 1** (the gap-filling pass), so that Step 2 is fully controlled by the
reviewed list.

### Messages: team vs developer

Every `Issue` has an `audience`. **`team`** messages are plain language (*what we found + what
to do*) and appear in the app and on **Needs Attention**. **`developer`** messages go only to
the **Technical Log**.

## Project layout

```
.
├── app.py                          # the research team's app (Streamlit)
├── ui.py  assets/                  # branding: ASICS header, styles, Janaagraha logo
├── Start ASICS.command / .bat      # double-click launchers
├── data/
│   ├── question_banks/Parastatal_ASICS_Question_Bank.xlsx
│   └── cities/ASICS_Cities_and_Parastatals.xlsx   # the city register (team-owned)
├── agent_setup/                    # verticals, agents, prompts, skills, team memory (Markdown)
├── agent_setup_page.py             # the app's Agent setup page
├── city_view_page.py               # the app's City files view (read-only)
├── docs/source_prompts/            # the original prompt the rules come from
├── scoring_page.py                 # the app's Step 3 · Score and Scores pages
├── scoring/2027/                   # scoring workbooks: templates, interns' copies, merged, AI, results
├── scripts/  run_pipeline.py  recheck_links.py  create_city_register.py
│             scoring.py  make_scoring_skeleton.py
├── src/asics_agent/
│   ├── agents/
│   │   ├── sources_master.py  answers_master.py  # the two master agents
│   │   ├── initial_checks.py  parastatal_discovery.py  links_builder.py
│   │   ├── sections/           # answer agent per section (base.py; sc.py adds a code check)
│   │   ├── rollup.py  final_qa.py  common.py  state.py
│   ├── links/                  # registry, accessibility, trust, text + quote location, SQLite
│   ├── sources_workbook.py     # the Step 1 → Step 2 handoff
│   ├── workbook.py             # answers workbook, index, checks report
│   ├── cities.py  runner.py  reporting.py  recheck.py  practice.py
│   ├── plan.py                 # one run across verticals, cities and steps (Run steps page)
│   ├── agent_setup.py          # reads agent_setup/: agents, prompts, skills, memory
│   ├── verticals.py            # reads agent_setup/verticals/: each vertical's settings
│   ├── tools/                  # our own tools (check_link, read_citation, …)
│   ├── scoring/                # Step 3: template reader, draft generator, phase2 (readiness +
│   │                           # evidence), interns' copies + merge, LibreOffice recalculation,
│   │                           # AI scorer, scores + results, workflow
│   ├── run_options.py          # per-run options (LangGraph context_schema)
│   └── applicability.py  question_bank.py  llm.py  services.py  models.py  config.py  progress.py
└── tests/                      # offline tests (practice mode)
```

## Adding a new section (e.g. a new pillar in the question bank)

A **section** is a part of the question bank, identified by the prefix of its question IDs
(UPD, DPG, SC). This is different from an ASICS **vertical** such as Parastatal or Mobility,
which is a whole assessment area with its own memory folder.

1. Add the questions to the question bank under a section header ending in the code, e.g. `(ELPR)`.
2. Add `agent_setup/skills/sections/elpr.md`:

   ```markdown
   ---
   name: ELPR
   title: Empowered & Legitimate Political Representation
   evidence_hints: board members elected councillors nominated chairperson notification
   ---
   - Board composition: name the section of the Act that sets out membership and say how
     many members are elected representatives.
   ```

Step 2 then gets an `answer_ELPR` agent automatically, and its questions are answered with
that guidance. Step 1 needs no change. Python is needed only for code-level checks:

| Need | How |
|---|---|
| Section instructions | the body of `skills/sections/<code>.md` |
| Better passage selection from long Acts or PDFs | `evidence_hints` in its settings block |
| Check or adjust each answer in code | a module in `src/asics_agent/agents/sections/` calling `register(SectionSpec(code="ELPR", postprocess=fn))`. See `require_figures` in [sc.py](src/asics_agent/agents/sections/sc.py) |
| A completely different workflow | `SectionSpec(build=fn)`, which receives an `AnswerTask` whose `citation_sources` are the only sources it may use |

## Verticals (Parastatal, UPD and new ones)

Every vertical runs the same Steps 1, 2 and 3 with the same code. What differs is
configuration: one settings file per vertical in `agent_setup/verticals/`, read by
[verticals.py](src/asics_agent/verticals.py). The app's sidebar lists every file there, and
`scripts/run_pipeline.py --vertical upd` runs one from the command line.

```yaml
---
name: upd                       # file name and folder name
title: UPD                      # shown in the app
code: UPD                       # scoring workbook prefix (UPD_SUMMARY_RAW…) and file names
unit: city_government           # what is assessed in each city (see below)
question_bank: scoring/2027/templates/ASICS_2027_UPD_Scoring_Workbook_v2.xlsx
question_bank_sheet: "UPD Questions_290926 "  # optional: which sheet
question_columns:               # optional: our column name -> the bank's own column name
  City-Systems Pillar: ASICS 2027_Report_Q No
  Tag: MQ_SQ
  Score / Max Score: Max Score
outputs: verticals/upd          # city folders go in outputs/verticals/upd/cities/<City>/
scoring_workbook: scoring/2027/templates/ASICS_2027_UPD_Scoring_Workbook_v2.xlsx
shared_rules: shared-rules-city # prompts/<name>.md: the rules every agent of this vertical gets
steps:                          # which agent does each job (agents/<name>.md)
  1: {profile: city-profiler, sources: city-citation-builder, assess: source-assessor}
  2: {answer: city-answer-writer}
  3: {score: question-scorer}
---
What the vertical assesses, in plain words.
```

**The unit** is what is assessed in each city:

| `unit` | Step 1 | Scoring workbook rows |
|---|---|---|
| `parastatal` | the agent **discovers** the parastatals (`discover` job), the team reviews them, then each is profiled | one per city and agency (`Bengaluru – BWSSB`) |
| `city_government` | no discovery: the unit is the **city government** (its ULG, from the city register, ID `ULG`), profiled the same way | one per city |

**The jobs** each step needs, and their default agents (any job not listed in `steps` uses the
default): Step 1 `discover` (parastatal-discovery, only for `unit: parastatal`), `profile`
(website-profiler), `sources` (citation-builder), `assess` (source-assessor); Step 2 `answer`
(answer-writer); Step 3 `score` (question-scorer); checks `bank_review`
(question-bank-reviewer). Giving a vertical its own agent for a job is how its research is
changed, e.g. UPD's `city-citation-builder` looks for state planning Acts and master plans,
not parastatal budgets. An agent's file names its prompt, skills, tools and model, as usual.

**Section guidance** for a vertical goes in `skills/sections/<vertical>/<code>.md` (e.g.
`skills/sections/upd/upd.md`); without one, the shared `skills/sections/<code>.md` is used.

**Kept apart per vertical:** city folders (Sources workbooks, answers, evidence), answers files
(`ASICS_<Title>_<City>_Phase2.xlsx`), practice runs, team memory
(`memory/verticals/<name>/`), and Step 3's AI copy (`scoring/2027/ai/<CODE>_ai.xlsx`). **Shared:**
the city register, the agents and prompts the verticals choose to share, and the results
workbook, which shows every vertical side by side.

Parastatal's file names exactly what ran before this was configurable (same question bank,
agents, rules and `outputs/cities/` folders), so nothing about it changed.

### Adding a vertical (e.g. Mobility)

1. **Question bank.** Put it in `data/question_banks/` (or point at a sheet of another
   workbook). It needs a question ID, question, MQ/SQ tag, max score, assessment level and
   detailed methodology; map its column names with `question_columns`. Applicability and
   evidence columns are optional (without Applicability, every question applies).
2. **Settings file.** Copy `agent_setup/verticals/upd.md` (city-level) or `parastatal.md`
   (agency-level) to `agent_setup/verticals/mobility.md` and edit it.
3. **Agents and prompts.** Start with the shared ones. When the research differs, copy an agent
   and its prompt (e.g. `agents/city-citation-builder.md` and `prompts/find-city-sources.md`),
   rewrite the prompt for the vertical, and name the new agent in `steps`. Keep the prompt's
   first line (`TASK: …`) and its JSON keys: the code reads them.
4. **Memory.** Add the vertical on the **Agent setup** page (or a folder
   `agent_setup/memory/verticals/mobility/`).
5. **Scoring workbook.** See [Scoring a new vertical](#scoring-a-new-vertical), then set
   `scoring_workbook`.
6. **Check it.** Choose the vertical in the app, run **Question bank check** (free), then a
   practice Step 1. `uv run pytest` includes a test that every vertical's settings are complete.

## Scoring a new vertical

1. Put the experts' workbook in `scoring/2027/templates/`, following the UPD layout: sheets
   named by question code with the code in B1; details above the header row; the row above
   the header says what to enter ("SELECT YES / NO", "ENTER A WHOLE NUMBER", "DO NOT ALTER
   FORMULA"…); a header row starting with **City**; the columns **Points (Auto-generate)**
   and **SCORER COMMENTS**; and a `<VERTICAL>_SUMMARY_RAW` sheet with an
   `<VERTICAL>_OVERALL_SCORE` row. ([scoring/template.py](src/asics_agent/scoring/template.py)
   reads it.) If only a methodology sheet exists, `scripts/make_scoring_skeleton.py` drafts one.
2. Add the vertical and file name to the **Verticals** sheet of the assignments workbook.
3. Press **Check workbooks**. No code changes are needed for people's scoring: assignment,
   merge and results work the same for every vertical.
4. AI scoring (Step 3) uses the vertical's own Steps 1 and 2, so the vertical needs a
   settings file in `agent_setup/verticals/` with `scoring_workbook` set (it then doesn't need
   to be on the Verticals sheet). The workbook's row labels must be the city (`unit:
   city_government`) or `City – Agency ID` (`unit: parastatal`).
   [scoring/phase2.py](src/asics_agent/scoring/phase2.py) decides whether a city is ready and
   loads its evidence.

## Other common changes

- **Look and branding:**
  - Colours and font are in `.streamlit/config.toml` (`[theme]`). The ink colour comes from the Janaagraha logo; set `primaryColor` and `linkColor` to official brand colours if you have them.
  - The logo is `assets/janaagraha-logo.svg`.
  - The ASICS page header and the small shared styles are in [ui.py](ui.py).

- **New city:** the team adds a row to the city register.
- **New parastatal type:** add it to `TYPES` in [cities.py](src/asics_agent/cities.py) and give it a rule in [applicability.py](src/asics_agent/applicability.py).
- **Website scoring:** the weights and bands are at the top of [links/trust.py](src/asics_agent/links/trust.py).
- **Prompts, skills, agents:** `agent_setup/` (see [agent_setup/README.md](agent_setup/README.md)). Each vertical's `shared_rules` prompt goes to every one of its agents (`prompts/shared-rules.md` for Parastatal).
- **Settings:** `.env`; see `.env.example`.

## Limitations

- **The accessibility test uses plain HTTP requests.** JavaScript-only pages end up as *Human Verification Required*.
- **Backlinks come from government pages the agent fetched during research,** not from a full web-wide backlink index. Official social handles are matched only when a government page links to the same handle.
- **Time limits:** each web page download is limited to 60 seconds and 30 MB (`links/accessibility.py`), and each Claude call to `ASICS_LLM_CALL_TIMEOUT` seconds (default 900). These exist because httpx's timeout applies per network read, so a slowly trickling server once froze a whole run. Live progress comes from `progress.report()` through LangGraph's `custom` stream mode.
- **A run in progress lives in the app's memory.** Closing the black window mid-run loses that run, but files already written are kept.
- **Sheet names:** Excel limits them to 31 characters, so long city names get "Scoring - &lt;City&gt;".
- **Question bank data issues** (e.g. UPD 1a and 1b score out of 10 but have a max of 5) show up in **Needs Attention**.

## Development

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run ruff format .
```
